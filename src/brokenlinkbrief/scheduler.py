"""Scheduler configuration and service for broken-link-brief.

Provides cron-based scheduling with SQLite persistence, including
ProjectSchedule/ScheduleState dataclasses, SchedulerService lifecycle,
and the existing Schedule/ScheduleStore for lightweight schedule leasing.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Cron expression parsing (returns dict with named fields)
# ---------------------------------------------------------------------------

_CRON_FIELDS = ("minute", "hour", "day", "month", "day_of_week")


def parse_cron_expression(expr: str) -> dict[str, str]:
    """Parse a 5-field cron expression into a dict with named keys.

    Args:
        expr: Cron expression (minute hour day month day_of_week).

    Returns:
        Dict with keys: minute, hour, day, month, day_of_week.

    Raises:
        ValueError: If the expression does not have exactly 5 fields,
            contains non-numeric values, or values are out of range.
    """
    if not expr or not expr.strip():
        raise ValueError("cron expression must not be empty")

    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have exactly 5 fields, got {len(fields)}"
        )

    result: dict[str, str] = {}
    for name, value in zip(_CRON_FIELDS, fields, strict=True):
        if value.startswith("*/"):
            num = value[2:]
            if not num.isdigit():
                raise ValueError(f"invalid cron field '{value}'")
        elif value == "*":
            pass
        elif not value.isdigit():
            raise ValueError(f"invalid cron field '{value}'")
        else:
            n = int(value)
            if name == "minute" and not (0 <= n <= 59):
                raise ValueError(f"minute out of range: {n}")
            if name == "hour" and not (0 <= n <= 23):
                raise ValueError(f"hour out of range: {n}")
            if name == "day" and not (1 <= n <= 31):
                raise ValueError(f"day out of range: {n}")
            if name == "month" and not (1 <= n <= 12):
                raise ValueError(f"month out of range: {n}")
            if name == "day_of_week" and not (0 <= n <= 7):
                raise ValueError(f"day_of_week out of range: {n}")
        result[name] = value

    return result


def validate_timezone(tz_name: str) -> bool:
    """Validate a timezone string using zoneinfo."""
    try:
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Scheduler DB schema
# ---------------------------------------------------------------------------


def create_scheduler_db_schema(conn: sqlite3.Connection) -> None:
    """Create the schedules table if it doesn't exist."""
    conn.execute("""CREATE TABLE IF NOT EXISTS schedules (
        project_id TEXT PRIMARY KEY,
        cron_expression TEXT NOT NULL,
        timezone TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        next_due REAL,
        lease_owner TEXT,
        lease_at REAL
    )""")


# ---------------------------------------------------------------------------
# ProjectSchedule — validated project configuration for the scheduler
# ---------------------------------------------------------------------------


@dataclass
class ProjectSchedule:
    """A project's scheduling configuration."""

    project_id: str
    name: str
    cron_expression: str
    timezone: str
    urls: list[str] = field(default_factory=list)
    timeout: float = 30.0
    max_workers: int = 10
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None


# ---------------------------------------------------------------------------
# ScheduleState — persisted state for a schedule row
# ---------------------------------------------------------------------------


@dataclass
class ScheduleState:
    """Persisted state of a project schedule in SQLite."""

    project_id: str
    cron_expression: str
    timezone: str
    enabled: bool
    next_due: float
    lease_owner: str | None = None
    lease_at: float | None = None


# ---------------------------------------------------------------------------
# SchedulerService — lifecycle manager for project schedules
# ---------------------------------------------------------------------------


class SchedulerService:
    """Manage project schedules with SQLite persistence and lifecycle."""

    def __init__(self, db_path: str | Path = "scheduler.db") -> None:
        self._db_path = str(db_path)
        self._running = False
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._mem_name: str = ""

    @property
    def db_path(self) -> str:
        """Path to the SQLite database."""
        return self._db_path

    @property
    def project_count(self) -> int:
        """Number of projects currently scheduled."""
        if not self._running or self._conn is None:
            return 0
        row = self._conn.execute("SELECT COUNT(*) FROM schedules").fetchone()
        return row[0] if row else 0

    def start(self) -> None:
        """Start the scheduler, creating DB tables if needed.

        Raises:
            RuntimeError: If already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("scheduler is already running")

            if self._db_path == ":memory:":
                uid = uuid.uuid4().hex
                self._mem_name = f"file:sched_{uid}?mode=memory&cache=shared"
                self._conn = sqlite3.connect(
                    self._mem_name,
                    uri=True,
                    timeout=10,
                    check_same_thread=False,
                )
            else:
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(
                    self._db_path,
                    timeout=10,
                    check_same_thread=False,
                )

            self._conn.row_factory = sqlite3.Row
            create_scheduler_db_schema(self._conn)
            self._running = True

    def stop(self, timeout: float = 30.0) -> None:
        """Stop the scheduler and close the database connection.

        Raises:
            RuntimeError: If not running.
        """
        with self._lock:
            if not self._running:
                raise RuntimeError("scheduler is not running")
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._running = False

    def add_project(self, config: ProjectSchedule) -> None:
        """Add or update a project schedule."""
        if not self._running or self._conn is None:
            raise RuntimeError("scheduler is not running")

        try:
            parse_cron_expression(config.cron_expression)
        except ValueError as e:
            raise ValueError(f"cron expression is invalid: {e}") from e

        if not validate_timezone(config.timezone):
            raise ValueError(f"timezone is invalid: {config.timezone}")

        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO schedules
                (project_id, cron_expression, timezone, enabled, next_due)
                VALUES (?, ?, ?, ?, NULL)""",
                (
                    config.project_id,
                    config.cron_expression,
                    config.timezone,
                    1 if config.enabled else 0,
                ),
            )
            self._conn.commit()

    def remove_project(self, project_id: str) -> bool:
        """Remove a project schedule."""
        if not self._running or self._conn is None:
            raise RuntimeError("scheduler is not running")

        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM schedules WHERE project_id=?", (project_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def get_project_schedule(self, project_id: str) -> ProjectSchedule | None:
        """Get a project schedule by ID."""
        if not self._running or self._conn is None:
            return None

        row = self._conn.execute(
            "SELECT * FROM schedules WHERE project_id=?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return ProjectSchedule(
            project_id=row["project_id"],
            name=row["project_id"],
            cron_expression=row["cron_expression"],
            timezone=row["timezone"],
            enabled=bool(row["enabled"]),
        )

    def list_projects(self) -> list[ProjectSchedule]:
        """List all scheduled projects."""
        if not self._running or self._conn is None:
            return []

        rows = self._conn.execute("SELECT * FROM schedules").fetchall()
        return [
            ProjectSchedule(
                project_id=r["project_id"],
                name=r["project_id"],
                cron_expression=r["cron_expression"],
                timezone=r["timezone"],
                enabled=bool(r["enabled"]),
            )
            for r in rows
        ]

    def get_next_run_times(self) -> dict[str, datetime | None]:
        """Get the next scheduled run time for each project."""
        if not self._running or self._conn is None:
            return {}

        result: dict[str, datetime | None] = {}
        rows = self._conn.execute("SELECT * FROM schedules").fetchall()
        for row in rows:
            pid = row["project_id"]
            if not row["enabled"]:
                result[pid] = None
            else:
                result[pid] = None  # next_due not computed in simple schema
        return result

    def is_running(self) -> bool:
        """Return True if the scheduler is running."""
        return self._running


# ---------------------------------------------------------------------------
# Legacy Schedule / ScheduleStore (used by scheduled_projects.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Schedule:
    """A single schedule entry (legacy type used by scheduled_projects)."""

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

    def create(
        self,
        project_id: str,
        cadence: str,
        tz: str,
        *,
        next_due_at: float,
    ) -> Schedule:
        if not project_id.strip() or not cadence.strip():
            raise ValueError("project_id and cadence are required")
        ZoneInfo(tz)
        item = Schedule(
            uuid.uuid4().hex,
            project_id,
            cadence,
            tz,
            "ACTIVE",
            next_due_at,
        )
        with self._connect() as db:
            vals = tuple(item.__dict__.values())
            db.execute(
                "INSERT INTO schedules VALUES (?,?,?,?,?,?,NULL,NULL)",
                vals,
            )
        return item

    def list_active(self) -> list[Schedule]:
        """Return all ACTIVE schedules ordered by next_due_at."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM schedules WHERE state='ACTIVE' ORDER BY next_due"
            ).fetchall()
        return [
            Schedule(
                r["id"],
                r["project_id"],
                r["cadence"],
                r["timezone"],
                r["state"],
                r["next_due"],
            )
            for r in rows
        ]

    def claim_due(
        self,
        *,
        now: float,
        worker_id: str,
        limit: int = 10,
    ) -> list[Schedule]:
        if not worker_id or limit < 1:
            raise ValueError("worker_id and positive limit required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM schedules WHERE state='ACTIVE'"
                " AND next_due<=? AND lease_owner IS NULL"
                " ORDER BY next_due LIMIT ?",
                (now, limit),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE schedules SET lease_owner=?, lease_at=?,"
                    " state='RUNNING' WHERE id=?"
                    " AND lease_owner IS NULL",
                    (worker_id, now, row["id"]),
                )
        return [
            Schedule(
                r["id"],
                r["project_id"],
                r["cadence"],
                r["timezone"],
                "RUNNING",
                r["next_due"],
            )
            for r in rows
        ]
