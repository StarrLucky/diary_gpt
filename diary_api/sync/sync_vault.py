#!/usr/bin/env python3
"""Sync diary entries from SQLite to a GitHub repo as Obsidian-style .md files.

Three modes:
- export: write all entries as .md to a local directory + state file (no GitHub).
  Used for initial bulk push via plain git CLI.
- sync:   one-shot push of changed entries to GitHub via PyGithub Contents API.
- loop:   sync repeatedly with configurable interval (intended container entrypoint).

State file (vault_sync_state.json) tracks per-entry sha256 hashes so each run only
pushes entries whose rendered content actually changed.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def render(entry: dict) -> str:
    """Build the markdown body for one entry."""
    body = entry["voice_text"].rstrip()
    summary = (entry.get("summary") or "").strip()
    tags = (entry.get("tags") or "").strip()
    hashtags = " ".join(f"#{t.strip()}" for t in tags.split(",") if t.strip())

    parts = [
        "---",
        f"id: {entry['id']}",
        f"created_at: {entry['created_at']}",
    ]
    if summary:
        # YAML-safe — wrap in double quotes, escape internal double quotes
        safe_summary = summary.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'summary: "{safe_summary}"')
    parts.append("---")
    parts.append("")
    if summary:
        parts.append(f"> {summary}")
        parts.append("")
    parts.append(body)
    if hashtags:
        parts.extend(["", hashtags])
    return "\n".join(parts) + "\n"


def filename(entry: dict) -> str:
    return f"diary/{entry['created_at'][:10]}_{entry['id']}.md"


def file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fetch_entries(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, created_at, voice_text, tags, summary "
        "FROM diary_entries ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cmd_export(args) -> None:
    out = Path(args.out).expanduser()
    state = {"hashes": {}}
    entries = fetch_entries(args.db_path)
    for entry in entries:
        content = render(entry)
        path = out / filename(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        state["hashes"][str(entry["id"])] = file_hash(content)

    if args.state:
        Path(args.state).expanduser().write_text(json.dumps(state, indent=2))

    print(f"Exported {len(entries)} entries to {out}")
    if args.state:
        print(f"Wrote state to {args.state}")


def _commit_message(entry: dict, is_update: bool) -> str:
    summary = (entry.get("summary") or "").strip()
    snippet = summary[:60] if summary else "no summary"
    verb = "Update" if is_update else "Add"
    return f"{verb} entry {entry['id']}: {snippet}"


def _do_sync(db_path: str, state_path: Path) -> int:
    from github import Github
    from github.GithubException import UnknownObjectException

    token = os.environ["GITHUB_DIARY_TOKEN"]
    repo_name = os.environ["VAULT_REPO"]  # e.g. "yourname/diary-vault"

    state = {"hashes": {}}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("hashes", {})

    entries = fetch_entries(db_path)
    g = Github(token)
    repo = g.get_repo(repo_name)

    pushed = 0
    for entry in entries:
        eid = str(entry["id"])
        content = render(entry)
        h = file_hash(content)
        if state["hashes"].get(eid) == h:
            continue

        path = filename(entry)
        is_update = bool(state["hashes"].get(eid))
        msg = _commit_message(entry, is_update=is_update)

        try:
            existing = repo.get_contents(path)
            repo.update_file(path, msg, content, existing.sha)
        except UnknownObjectException:
            repo.create_file(path, msg, content)

        state["hashes"][eid] = h
        pushed += 1
        print(f"Pushed {path} ({msg})", flush=True)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Sync complete: {pushed} pushed, {len(entries)} total", flush=True)
    return pushed


def cmd_sync(args) -> None:
    state_path = Path(
        os.environ.get("VAULT_SYNC_STATE", "/app/state/vault_sync_state.json")
    )
    _do_sync(args.db_path, state_path)


def cmd_loop(args) -> None:
    interval = int(os.environ.get("VAULT_SYNC_INTERVAL", "60"))
    state_path = Path(
        os.environ.get("VAULT_SYNC_STATE", "/app/state/vault_sync_state.json")
    )
    print(f"Starting sync loop, interval={interval}s, state={state_path}", flush=True)
    while True:
        try:
            _do_sync(args.db_path, state_path)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR in sync: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=os.environ.get("DB_PATH", "/app/data/diary.db"),
        help="Path to diary.db",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="Bulk export to filesystem (no GitHub)")
    p_export.add_argument("--out", required=True, help="Vault directory")
    p_export.add_argument("--state", help="Optional path to write state file")
    p_export.set_defaults(func=cmd_export)

    p_sync = sub.add_parser("sync", help="One-shot sync to GitHub")
    p_sync.set_defaults(func=cmd_sync)

    p_loop = sub.add_parser("loop", help="Sync to GitHub repeatedly")
    p_loop.set_defaults(func=cmd_loop)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
