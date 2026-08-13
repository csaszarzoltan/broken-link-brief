"""Durable SQLite scan-job state, leases, recovery, and idempotency."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .projects import configured_project_db

TERMINAL = {"PARTIALLY_COMPLETED", "COMPLETED", "FAILED", "CANCELLED"}


def now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class JobConflict(ValueError):  # noqa: N818 — legacy public API name
    """Raised when a job action conflicts with the current job state."""


# Backwards-compatible alias (legacy name referenced by tests and callers).
JobConflictError = JobConflict


class JobLeaseLost(JobConflict):
    """Raised when a worker no longer owns the job lease."""


class ScanJobStore:
    """Persistent durable scan jobs with leases and idempotency keys."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or configured_project_db())
        self._migrate()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _migrate(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS scan_jobs (id TEXT PRIMARY KEY, "
                "project_id TEXT NOT NULL, project_name TEXT NOT NULL, "
                "origin TEXT NOT NULL, state TEXT NOT NULL, parent_job_id TEXT, "
                "policy_version INTEGER NOT NULL, created_at TEXT NOT NULL, "
                "started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL, "
                "cancel_requested_at TEXT, version INTEGER NOT NULL DEFAULT 1, "
                "error TEXT, worker_id TEXT, lease_expires_at TEXT, heartbeat_at TEXT, "
                "policy_snapshot_json TEXT)"
            )
            cols = {r[1] for r in db.execute("PRAGMA table_info(scan_jobs)")}
            for name, typ in [
                ("worker_id", "TEXT"),
                ("lease_expires_at", "TEXT"),
                ("heartbeat_at", "TEXT"),
                ("policy_snapshot_json", "TEXT"),
            ]:
                if name not in cols:
                    db.execute(f"ALTER TABLE scan_jobs ADD COLUMN {name} {typ}")
            db.execute(
                "CREATE TABLE IF NOT EXISTS scan_job_sources (id TEXT PRIMARY KEY, "
                "job_id TEXT NOT NULL, ordinal INTEGER NOT NULL,"
                " source_url TEXT NOT NULL,"
                " state TEXT NOT NULL, started_at TEXT, completed_at TEXT,"
                " result_json TEXT, error TEXT,"
                " attempts_count INTEGER NOT NULL DEFAULT 0, "
                "UNIQUE(job_id,source_url), "
                "FOREIGN KEY(job_id) REFERENCES scan_jobs(id) ON DELETE CASCADE)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS scan_job_idempotency ("
                "scope TEXT NOT NULL,key_hash TEXT NOT NULL,request_hash TEXT NOT NULL,"
                "job_id TEXT NOT NULL,PRIMARY KEY(scope,key_hash))"
            )

    def create(
        self,
        project_id: str,
        name: str,
        targets: list[str],
        policy_version: int = 0,
        origin: str = "MANUAL",
        parent_job_id: str | None = None,
        idempotency_key: str | None = None,
        scope: str = "default",
        policy_snapshot: dict | None = None,
    ) -> dict:
        """Create a job; returns the existing job when idempotency key matches."""
        req = hashlib.sha256(
            json.dumps(
                [project_id, targets, origin, parent_job_id], sort_keys=True
            ).encode()
        ).hexdigest()
        kh = hashlib.sha256((idempotency_key or uuid.uuid4().hex).encode()).hexdigest()
        with self._db() as db:
            if idempotency_key:
                old = db.execute(
                    "SELECT * FROM scan_job_idempotency WHERE scope=? AND key_hash=?",
                    (scope, kh),
                ).fetchone()
                if old:
                    if old["request_hash"] != req:
                        raise JobConflict(
                            "idempotency key reused for different request"
                        )
                    return self.get(old["job_id"])
            jid = uuid.uuid4().hex
            ts = now()
            db.execute(
                "INSERT INTO scan_jobs(id,project_id,project_name,origin,state,"
                "parent_job_id,policy_version,created_at,updated_at,version,"
                "policy_snapshot_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    project_id,
                    name,
                    origin,
                    "QUEUED",
                    parent_job_id,
                    policy_version,
                    ts,
                    ts,
                    1,
                    json.dumps(policy_snapshot, sort_keys=True)
                    if policy_snapshot
                    else None,
                ),
            )
            db.executemany(
                "INSERT INTO scan_job_sources(id,job_id,ordinal,source_url,state) "
                "VALUES (?,?,?,?,?)",
                [
                    (uuid.uuid4().hex, jid, i, u, "PENDING")
                    for i, u in enumerate(targets)
                ],
            )
            if idempotency_key:
                db.execute(
                    "INSERT INTO scan_job_idempotency VALUES (?,?,?,?)",
                    (scope, kh, req, jid),
                )
        return self.get(jid)

    def get(self, jid: str) -> dict:
        """Return a job dict with source state counts."""
        with self._db() as db:
            row = db.execute("SELECT * FROM scan_jobs WHERE id=?", (jid,)).fetchone()
            if not row:
                raise KeyError(jid)
            counts = {
                r["state"]: r["n"]
                for r in db.execute(
                    "SELECT state,count(*) n FROM scan_job_sources "
                    "WHERE job_id=? GROUP BY state",
                    (jid,),
                )
            }
        d = dict(row)
        d.update(
            {
                f"{s.lower()}_count": counts.get(s, 0)
                for s in ["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
            }
        )
        d["target_count"] = sum(counts.values())
        return d

    def sources(self, jid: str, state: str | None = None) -> list[dict]:
        """Return the source rows of a job, optionally filtered by state."""
        with self._db() as db:
            sql = "SELECT * FROM scan_job_sources WHERE job_id=?"
            args: list[str] = [jid]
            if state:
                sql += " AND state=?"
                args.append(state)
            return [dict(r) for r in db.execute(sql + " ORDER BY ordinal", args)]

    def list(self, project_id: str | None = None) -> list[dict]:
        """Return all jobs, newest first, optionally filtered by project."""
        with self._db() as db:
            rows = db.execute(
                "SELECT id FROM scan_jobs"
                + (" WHERE project_id=?" if project_id else "")
                + " ORDER BY created_at DESC",
                ((project_id,) if project_id else ()),
            ).fetchall()
        return [self.get(r["id"]) for r in rows]

    def claim(
        self, worker_id: str = "default-worker", lease_seconds: int = 30
    ) -> dict | None:
        """Claim the next runnable job (expired lease first, then QUEUED)."""
        ts = datetime.now(timezone.utc)
        expiry = (ts + timedelta(seconds=lease_seconds)).isoformat()
        stamp = ts.isoformat()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute(
                "SELECT id FROM scan_jobs WHERE state='RUNNING' "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at<? "
                "ORDER BY created_at LIMIT 1",
                (stamp,),
            ).fetchone()
            if expired:
                jid = expired["id"]
                db.execute(
                    "UPDATE scan_job_sources SET state='PENDING',started_at=NULL "
                    "WHERE job_id=? AND state='RUNNING' AND result_json IS NULL",
                    (jid,),
                )
                db.execute(
                    "UPDATE scan_jobs SET worker_id=?,lease_expires_at=?,"
                    "heartbeat_at=?,updated_at=?,version=version+1 WHERE id=?",
                    (worker_id, expiry, stamp, stamp, jid),
                )
                return self.get(jid)
            row = db.execute(
                "SELECT id FROM scan_jobs WHERE state='QUEUED' "
                "ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE scan_jobs SET state='RUNNING',worker_id=?,lease_expires_at=?,"
                "heartbeat_at=?,started_at=COALESCE(started_at,?),updated_at=?,"
                "version=version+1 WHERE id=?",
                (worker_id, expiry, stamp, stamp, stamp, row["id"]),
            )
            return self.get(row["id"])

    def _owned(self, db: sqlite3.Connection, jid: str, worker: str) -> None:
        row = db.execute(
            "SELECT worker_id,state,lease_expires_at FROM scan_jobs WHERE id=?",
            (jid,),
        ).fetchone()
        if (
            not row
            or row["state"] != "RUNNING"
            or row["worker_id"] != worker
            or (row["lease_expires_at"] and row["lease_expires_at"] < now())
        ):
            raise JobLeaseLost("job lease is no longer owned")

    def heartbeat(self, jid: str, worker_id: str, lease_seconds: int = 30) -> dict:
        """Extend the lease of a job owned by worker_id."""
        stamp = datetime.now(timezone.utc)
        expiry = (stamp + timedelta(seconds=lease_seconds)).isoformat()
        with self._db() as db:
            self._owned(db, jid, worker_id)
            db.execute(
                "UPDATE scan_jobs SET heartbeat_at=?,lease_expires_at=?,updated_at=? "
                "WHERE id=?",
                (stamp.isoformat(), expiry, stamp.isoformat(), jid),
            )
        return self.get(jid)

    def force_lease_expiry(self, jid: str, value: str | None) -> None:
        """Force a lease expiry (test hook)."""
        with self._db() as db:
            db.execute(
                "UPDATE scan_jobs SET lease_expires_at=? WHERE id=?", (value, jid)
            )

    def start_source(self, sid: str, worker_id: str | None = None) -> None:
        """Mark a source as RUNNING, verifying ownership when a worker is given."""
        with self._db() as db:
            row = db.execute(
                "SELECT job_id FROM scan_job_sources WHERE id=?", (sid,)
            ).fetchone()
            if worker_id:
                self._owned(db, row["job_id"], worker_id)
            db.execute(
                "UPDATE scan_job_sources SET state='RUNNING',started_at=? "
                "WHERE id=? AND state='PENDING'",
                (now(), sid),
            )

    def finish_source(self, sid: str, *args, **kwargs) -> None:
        """Mark a source COMPLETED/FAILED with result and error details."""
        worker: str | None = None
        if args and isinstance(args[0], str):
            worker = args[0]
            args = args[1:]
        ok = args[0] if args else kwargs.pop("ok")
        result = args[1] if len(args) > 1 else kwargs.get("result")
        error = kwargs.get("error")
        attempts = kwargs.get("attempts", 0)
        with self._db() as db:
            row = db.execute(
                "SELECT job_id FROM scan_job_sources WHERE id=?", (sid,)
            ).fetchone()
            if worker:
                self._owned(db, row["job_id"], worker)
            db.execute(
                "UPDATE scan_job_sources SET state=?,completed_at=?,result_json=?,"
                "error=?,attempts_count=? WHERE id=? AND state='RUNNING'",
                (
                    "COMPLETED" if ok else "FAILED",
                    now(),
                    json.dumps(result) if result is not None else None,
                    error,
                    attempts,
                    sid,
                ),
            )

    def finalize(self, jid: str) -> dict:
        """Move a job to a terminal state based on its sources."""
        src = self.sources(jid)
        failed = sum(x["state"] == "FAILED" for x in src)
        done = sum(x["state"] == "COMPLETED" for x in src)
        state = (
            "COMPLETED"
            if done == len(src)
            else "FAILED"
            if failed == len(src)
            else "PARTIALLY_COMPLETED"
        )
        with self._db() as db:
            db.execute(
                "UPDATE scan_jobs SET state=?,completed_at=?,updated_at=?,"
                "worker_id=NULL,lease_expires_at=NULL,version=version+1 "
                "WHERE id=? AND state NOT IN (?,?,?,?)",
                (state, now(), now(), jid, *TERMINAL),
            )
        return self.get(jid)

    def cancel(self, jid: str, version: int) -> dict:
        """Request cancellation; immediately cancels QUEUED jobs."""
        job = self.get(jid)
        if job["version"] != version:
            raise JobConflict("job version conflict")
        if job["state"] in TERMINAL:
            raise JobConflict("terminal job cannot be cancelled")
        ts = now()
        with self._db() as db:
            db.execute(
                "UPDATE scan_jobs SET state='CANCEL_REQUESTED',"
                "cancel_requested_at=?,updated_at=?,version=version+1 WHERE id=?",
                (ts, ts, jid),
            )
            if job["state"] == "QUEUED":
                db.execute(
                    "UPDATE scan_job_sources SET state='CANCELLED',completed_at=? "
                    "WHERE job_id=? AND state='PENDING'",
                    (ts, jid),
                )
                db.execute(
                    "UPDATE scan_jobs SET state='CANCELLED',completed_at=?,"
                    "version=version+1 WHERE id=?",
                    (ts, jid),
                )
        return self.get(jid)
