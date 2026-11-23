"""SQLite persistence for the monitor state and the outage history."""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at   REAL
);
CREATE INDEX IF NOT EXISTS outages_started_at ON outages (started_at);
"""


@dataclass(frozen=True)
class Outage:
    started_at: float
    ended_at: float | None

    def duration(self, now: float) -> float:
        end = self.ended_at if self.ended_at is not None else now
        return max(0.0, end - self.started_at)


class Storage:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        with self._lock:
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    # -- key/value state -------------------------------------------------

    def get(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # -- outages ---------------------------------------------------------

    def open_outage(self, started_at: float) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO outages (started_at) VALUES (?)", (started_at,))

    def current_outage(self) -> Outage | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT started_at, ended_at FROM outages "
                "WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return Outage(*row) if row else None

    def close_outage(self, ended_at: float) -> Outage | None:
        """Close the open outage (if any) and return it."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, started_at FROM outages WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            outage_id, started_at = row
            self._conn.execute(
                "UPDATE outages SET ended_at = ? WHERE id = ?", (ended_at, outage_id)
            )
        return Outage(started_at, ended_at)

    def recent_outages(self, limit: int = 10) -> list[Outage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT started_at, ended_at FROM outages ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Outage(*row) for row in rows]

    def outages_since(self, since: float) -> list[Outage]:
        """Outages that started after `since` or were still ongoing at that time."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT started_at, ended_at FROM outages "
                "WHERE started_at >= ? OR ended_at IS NULL OR ended_at >= ? "
                "ORDER BY started_at",
                (since, since),
            ).fetchall()
        return [Outage(*row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
