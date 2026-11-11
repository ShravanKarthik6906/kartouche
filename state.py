"""
A small SQLite database for web-app state that must survive a page refresh
or a server restart: jobs, the daily spending ledger and rate-limit events.
(The per-document translation data lives separately, in each job's own
kartouche.db.)
"""

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS spend (
    day TEXT PRIMARY KEY,           -- UTC date, YYYY-MM-DD
    usd REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rate_events (
    id INTEGER PRIMARY KEY,
    visitor TEXT NOT NULL,
    kind TEXT NOT NULL,             -- 'upload' | 'sample'
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rate_events_lookup ON rate_events (visitor, kind, ts);
"""


class StateDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self):
        with self._lock:
            self._conn.close()
