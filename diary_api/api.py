import math
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Diary API", version="5.0.0")

DB_PATH = os.getenv("DB_PATH", "data/diary.db")
API_KEY = os.getenv("DIARY_API_KEY", "")

# --- DB helpers ---

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS diary_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,
    voice_text  TEXT    NOT NULL,
    duration    INTEGER DEFAULT 0,
    message_id  INTEGER DEFAULT 0,
    tags        TEXT    DEFAULT '',
    summary     TEXT    DEFAULT ''
)
"""
_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_user_date
ON diary_entries(user_id, created_at)
"""


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(diary_entries)")}
    if "summary" not in cols:
        conn.execute("ALTER TABLE diary_entries ADD COLUMN summary TEXT DEFAULT ''")


def _get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_INDEX)
    _migrate(conn)
    return conn


# --- Auth ---

def _check_key(x_api_key: str = Header(...)):
    if not API_KEY:
        raise HTTPException(500, "API key not configured on server")
    if x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key")


# --- Models ---

class TagStat(BaseModel):
    tag: str
    count: int


class StatsOut(BaseModel):
    total_entries: int
    date_range: str
    tags: list[TagStat]


class EntrySummary(BaseModel):
    id: int
    created_at: str
    summary: str
    tags: str = ""


class SummaryPage(BaseModel):
    page: int
    total_pages: int
    total_entries: int
    entries: list[EntrySummary]


class EntryFull(BaseModel):
    id: int
    created_at: str
    voice_text: str
    tags: str = ""
    summary: str = ""


class EntryIn(BaseModel):
    voice_text: str
    tags: str = ""
    summary: str = ""


# --- Routes ---

PAGE_SIZE = 50  # ~250 chars per entry with preview = ~12.5k per page, safe under 100k


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats", response_model=StatsOut)
def get_stats(x_api_key: str = Header(...)):
    """Overview: total entries, date range, tag counts. Call this FIRST."""
    _check_key(x_api_key)
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM diary_entries").fetchone()[0]
    dr = db.execute("SELECT MIN(created_at), MAX(created_at) FROM diary_entries").fetchone()
    date_range = f"{dr[0] or 'N/A'} to {dr[1] or 'N/A'}"
    rows = db.execute("SELECT tags FROM diary_entries").fetchall()
    db.close()
    c = Counter()
    for r in rows:
        for t in (r[0] or "").split(","):
            t = t.strip()
            if t:
                c[t] += 1
    return StatsOut(
        total_entries=total,
        date_range=date_range,
        tags=[TagStat(tag=tag, count=count) for tag, count in c.most_common()],
    )


@app.get("/entries/summary", response_model=SummaryPage)
def get_summary(
    x_api_key: str = Header(...),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    page: int = Query(1, description="Page number (starts at 1)"),
):
    """Paginated summaries with preview text (200 chars). Returns page info so you know how many pages to fetch. Fetch ALL pages for full context."""
    _check_key(x_api_key)
    db = _get_db()

    # Count total
    if tag:
        total = db.execute(
            "SELECT COUNT(*) FROM diary_entries WHERE tags LIKE ?", (f"%{tag}%",)
        ).fetchone()[0]
    else:
        total = db.execute("SELECT COUNT(*) FROM diary_entries").fetchone()[0]

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    offset = (page - 1) * PAGE_SIZE

    if tag:
        rows = db.execute(
            "SELECT id, created_at, summary, tags FROM diary_entries WHERE tags LIKE ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (f"%{tag}%", PAGE_SIZE, offset),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, created_at, summary, tags FROM diary_entries ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (PAGE_SIZE, offset),
        ).fetchall()
    db.close()

    return SummaryPage(
        page=page,
        total_pages=total_pages,
        total_entries=total,
        entries=[dict(r) for r in rows],
    )


@app.get("/entries/{entry_id}", response_model=EntryFull)
def get_entry(entry_id: int, x_api_key: str = Header(...)):
    """Full text of one entry by ID."""
    _check_key(x_api_key)
    db = _get_db()
    row = db.execute(
        "SELECT id, created_at, voice_text, tags, summary FROM diary_entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Entry not found")
    return dict(row)


@app.get("/entries", response_model=list[EntryFull])
def get_entries(
    x_api_key: str = Header(...),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    limit: int = Query(10, description="Max entries"),
    offset: int = Query(0, description="Skip first N"),
):
    """Full entries with pagination."""
    _check_key(x_api_key)
    db = _get_db()
    if tag:
        rows = db.execute(
            "SELECT id, created_at, voice_text, tags, summary FROM diary_entries WHERE tags LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (f"%{tag}%", limit, offset),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, created_at, voice_text, tags, summary FROM diary_entries ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.post("/entries", response_model=EntryFull)
def create_entry(entry: EntryIn, x_api_key: str = Header(...)):
    _check_key(x_api_key)
    now = datetime.now(timezone.utc).isoformat()
    db = _get_db()
    cursor = db.execute(
        """INSERT INTO diary_entries (user_id, created_at, voice_text, duration, message_id, tags, summary)
           VALUES (?, ?, ?, 0, 0, ?, ?)""",
        (0, now, entry.voice_text, entry.tags, entry.summary),
    )
    db.commit()
    entry_id = cursor.lastrowid
    db.close()
    return EntryFull(
        id=entry_id,
        created_at=now,
        voice_text=entry.voice_text,
        tags=entry.tags,
        summary=entry.summary,
    )
