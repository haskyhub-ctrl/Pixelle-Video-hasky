# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
SQLite persistence for niche research: saved niches, tracked channels with
subscriber snapshots (needed for growth rates), the content calendar and API
usage accounting.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_niches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    platforms TEXT,
    niche_score REAL,
    summary TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracked_channels (
    channel_id TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'youtube',
    title TEXT,
    is_mine INTEGER DEFAULT 0,
    data TEXT,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_snapshots (
    channel_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    subscribers INTEGER,
    total_views INTEGER,
    video_count INTEGER
);
CREATE INDEX IF NOT EXISTS idx_snap_channel ON channel_snapshots(channel_id, ts);
CREATE TABLE IF NOT EXISTS calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    platform TEXT DEFAULT 'youtube',
    scheduled_at TEXT NOT NULL,
    status TEXT DEFAULT 'idea',
    topic TEXT,
    script TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_usage (
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    requests INTEGER DEFAULT 0,
    units INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NicheStorage:
    def __init__(self, db_path: str = "data/niche.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    # ------------------------------------------------------------- niches

    def save_niche(self, query: str, platforms: list[str], niche_score: float, summary: dict) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO saved_niches(query, platforms, niche_score, summary, created_at) VALUES (?,?,?,?,?)",
                (query, ",".join(platforms), niche_score, json.dumps(summary, ensure_ascii=False, default=str), _now()))
            return cur.lastrowid

    def list_niches(self) -> list[dict]:
        rows = self._rows("SELECT * FROM saved_niches ORDER BY created_at DESC")
        for r in rows:
            r["summary"] = json.loads(r["summary"] or "{}")
        return rows

    def delete_niche(self, niche_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM saved_niches WHERE id=?", (niche_id,))

    # ----------------------------------------------------------- channels

    def track_channel(self, channel_id: str, title: str, platform: str = "youtube",
                      is_mine: bool = False, data: Optional[dict] = None) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO tracked_channels(channel_id, platform, title, is_mine, data, added_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(channel_id) DO UPDATE SET title=excluded.title,
                   is_mine=MAX(tracked_channels.is_mine, excluded.is_mine), data=excluded.data""",
                (channel_id, platform, title, int(is_mine), json.dumps(data or {}, default=str), _now()))

    def untrack_channel(self, channel_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM tracked_channels WHERE channel_id=?", (channel_id,))

    def list_channels(self, mine_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM tracked_channels"
        if mine_only:
            sql += " WHERE is_mine=1"
        rows = self._rows(sql + " ORDER BY added_at DESC")
        for r in rows:
            r["data"] = json.loads(r["data"] or "{}")
        return rows

    def add_snapshot(self, channel_id: str, subscribers: int, total_views: int, video_count: int) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO channel_snapshots VALUES (?,?,?,?,?)",
                      (channel_id, _now(), subscribers, total_views, video_count))

    def snapshots(self, channel_id: str) -> list[dict]:
        rows = self._rows("SELECT * FROM channel_snapshots WHERE channel_id=? ORDER BY ts", (channel_id,))
        for r in rows:
            r["ts"] = datetime.fromisoformat(r["ts"])
        return rows

    # ----------------------------------------------------------- calendar

    def add_calendar(self, title: str, scheduled_at: datetime, platform: str = "youtube",
                     status: str = "idea", topic: str = "", script: str = "", notes: str = "") -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO calendar(title, platform, scheduled_at, status, topic, script, notes, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (title, platform, scheduled_at.isoformat(), status, topic, script, notes, _now()))
            return cur.lastrowid

    def update_calendar(self, item_id: int, **fields: Any) -> None:
        allowed = {"title", "platform", "scheduled_at", "status", "topic", "script", "notes"}
        sets = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items() if k in allowed}
        if not sets:
            return
        with self._conn() as c:
            c.execute(f"UPDATE calendar SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                      (*sets.values(), item_id))

    def delete_calendar(self, item_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM calendar WHERE id=?", (item_id,))

    def list_calendar(self) -> list[dict]:
        return self._rows("SELECT * FROM calendar ORDER BY scheduled_at")

    # -------------------------------------------------------------- usage

    def log_usage(self, source: str, requests: int = 0, units: int = 0, cost_usd: float = 0.0) -> None:
        if not (requests or units or cost_usd):
            return
        with self._conn() as c:
            c.execute("INSERT INTO api_usage VALUES (?,?,?,?,?)", (_now(), source, requests, units, cost_usd))

    def usage_today(self) -> dict[str, dict]:
        today = datetime.now(timezone.utc).date().isoformat()
        rows = self._rows(
            """SELECT source, SUM(requests) AS requests, SUM(units) AS units, SUM(cost_usd) AS cost_usd
               FROM api_usage WHERE ts >= ? GROUP BY source""", (today,))
        return {r["source"]: r for r in rows}
