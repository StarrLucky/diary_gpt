#!/usr/bin/env python3
"""Export diary entries from SQLite to .md files for an Obsidian vault.

Each entry becomes vault/diary/{YYYY-MM-DD}_{id}.md with YAML frontmatter
and inline #hashtags converted from the comma-separated tags column.

Idempotent: re-running overwrites files by id.
"""

import argparse
import sqlite3
from pathlib import Path


def _format_entry(entry_id: int, created_at: str, voice_text: str, tags: str) -> str:
    hashtags = " ".join(f"#{t.strip()}" for t in tags.split(",") if t.strip())
    body = voice_text.rstrip()
    parts = [
        "---",
        f"id: {entry_id}",
        f"created_at: {created_at}",
        "---",
        "",
        body,
    ]
    if hashtags:
        parts.extend(["", hashtags])
    return "\n".join(parts) + "\n"


def _filename(entry_id: int, created_at: str) -> str:
    date_part = created_at[:10]  # YYYY-MM-DD
    return f"{date_part}_{entry_id}.md"


def export(db_path: Path, vault_dir: Path) -> int:
    diary_dir = vault_dir / "diary"
    diary_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, created_at, voice_text, tags "
        "FROM diary_entries ORDER BY created_at"
    ).fetchall()
    conn.close()

    for row in rows:
        content = _format_entry(row["id"], row["created_at"], row["voice_text"], row["tags"] or "")
        path = diary_dir / _filename(row["id"], row["created_at"])
        path.write_text(content, encoding="utf-8")

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, required=True, help="Path to diary.db")
    parser.add_argument("--vault-dir", type=Path, required=True, help="Obsidian vault directory")
    args = parser.parse_args()

    count = export(args.db_path, args.vault_dir)
    print(f"Exported {count} entries to {args.vault_dir / 'diary'}")


if __name__ == "__main__":
    main()
