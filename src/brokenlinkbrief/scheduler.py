"""Durable project schedules backed by SQLite."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Schedule:
    id: str
    project_id: str
    cadence: str
    timezone: str
    state: str
    next_due_at: float


class ScheduleStore:
    """Persist schedules and atomically lease due work across restarts."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, cadence TEXT NOT NULL,
                timezone TEXT NOT NULL, state TEXT NOT NULL, next_due REAL NOT NULL,
                lease_owner TEXT, lease_at REAL)""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create(self, project_id: str, cadence: str, timezone: str, *, next_due_at: float) -> Schedule:
        if not project_id.strip() or not cadence.strip():
            raise ValueError("project_id and cadence are required")
        ZoneInfo(timezone)
        item = Schedule(uuid.uuid4().hex, project_id, cadence, timezone, "ACTIVE", next_due_at)
        with self._connect() as db:
            db.execute("INSERT INTO schedules VALUES (?,?,?,?,?,?,NULL,NULL)", tuple(item.__dict__.values()))
        return item

    def claim_due(self, *, now: float, worker_id: str, limit: int = 10) -> list[Schedule]:
        if not worker_id or limit < 1:
            raise ValueError("worker_id and positive limit required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM schedules WHERE state='ACTIVE' AND next_due<=? AND lease_owner IS NULL ORDER BY next_due LIMIT ?",
                (now, limit),
            ).fetchall()
            for row in rows:
                db.execute("UPDATE schedules SET lease_owner=?, lease_at=?, state='RUNNING' WHERE id=? AND lease_owner IS NULL", (worker_id, now, row["id"]))
        return [Schedule(r["id"], r["project_id"], r["cadence"], r["timezone"], "RUNNING", r["next_due"]) for r in rows]
