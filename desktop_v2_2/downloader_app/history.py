from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable

from .models import VideoItem


class HistoryStore:
    """Tiny local SQLite download history.

    Only download metadata is stored. Browser session/cookie/header values are
    deliberately never persisted.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    page_url TEXT,
                    title TEXT,
                    source TEXT,
                    quality TEXT,
                    filename TEXT,
                    completed_at REAL NOT NULL,
                    size_bytes INTEGER DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_url ON downloads(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_completed ON downloads(completed_at DESC)")

    def add_completed(self, item: VideoItem, quality: str, filename: str) -> int:
        size = 0
        try:
            path = Path(filename)
            if path.is_file():
                size = path.stat().st_size
        except Exception:
            pass
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO downloads(url,page_url,title,source,quality,filename,completed_at,size_bytes)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    item.active_url(),
                    item.page_url,
                    item.title,
                    item.source,
                    quality,
                    filename,
                    time.time(),
                    size,
                ),
            )
            return int(cur.lastrowid or 0)

    def find_existing(self, item: VideoItem):
        urls = [value for value in {item.active_url(), item.webpage_url, item.page_url} if value]
        if not urls:
            return None
        placeholders = ",".join("?" for _ in urls)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM downloads WHERE url IN ({placeholders}) OR page_url IN ({placeholders}) ORDER BY completed_at DESC LIMIT 1",
                tuple(urls + urls),
            ).fetchone()
            if not row:
                return None
            filename = str(row["filename"] or "")
            if filename and not Path(filename).exists():
                return None
            return dict(row)

    def recent(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM downloads ORDER BY completed_at DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def clear(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM downloads")
