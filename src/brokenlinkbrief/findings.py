"""Durable project findings, evidence, occurrences, verification, and audit."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from brokenlinkbrief.projects import configured_project_db

STATES = frozenset({"OPEN", "ACKNOWLEDGED", "IGNORED", "RESOLVED"})
CLASSIFICATIONS = frozenset(
    {
        "UNVERIFIED",
        "TRANSIENT",
        "BOT_BLOCKED",
        "RECOVERED",
        "INCONCLUSIVE",
        "CONFIRMED_BROKEN",
    }
)
_SECRET_RE = re.compile(r"(?i)(authorization|cookie|password|token|secret)=?[^\s&]*")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_error(value: str | None) -> str | None:
    if not value:
        return None
    return _SECRET_RE.sub(r"\1=[redacted]", value)[:200]


class VersionConflict(ValueError):
    """Raised when a finding mutation uses a stale version."""


class FindingStore:
    """SQLite persistence for project-scoped findings and audit evidence."""

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
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_findings(
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    latest_status INTEGER,
                    classification TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'OPEN',
                    assignee TEXT,
                    ignore_reason TEXT,
                    ignore_expiry TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    resolved_at TEXT,
                    latest_verification_at TEXT,
                    latest_verification_outcome TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(project_id,target_url),
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS finding_occurrences(
                    id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    anchor_text TEXT NOT NULL,
                    context TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(finding_id,source_url,fingerprint),
                    FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS finding_evidence(
                    id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status INTEGER,
                    error TEXT,
                    latency_seconds REAL NOT NULL,
                    sequence INTEGER NOT NULL,
                    classification TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS finding_verifications(
                    id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    source_checked INTEGER NOT NULL,
                    source_present INTEGER NOT NULL,
                    failures_json TEXT NOT NULL,
                    FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS finding_audit_events(
                    id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    old_state TEXT,
                    new_state TEXT,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_pf_project_state
                    ON project_findings(project_id,state,last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_fo_finding
                    ON finding_occurrences(finding_id,active);
                CREATE INDEX IF NOT EXISTS idx_fe_finding
                    ON finding_evidence(finding_id,observed_at);
                CREATE INDEX IF NOT EXISTS idx_fa_finding
                    ON finding_audit_events(finding_id,created_at);
                """
            )

    def ensure_project(self, project_id: str, name: str = "Project") -> None:
        """Create a minimal project for isolated embedding and tests."""
        now = _now()
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS projects(
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0
                )"""
            )
            db.execute(
                "INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?)",
                (project_id, name, 0, now, now, 0),
            )

    def _row(self, db: sqlite3.Connection, finding_id: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM project_findings WHERE id=?", (finding_id,)
        ).fetchone()
        if row is None:
            raise KeyError(finding_id)
        return row

    def _audit(
        self,
        db: sqlite3.Connection,
        finding_id: str,
        event: str,
        old_state: str | None,
        new_state: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        db.execute(
            "INSERT INTO finding_audit_events VALUES(?,?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                finding_id,
                event,
                _now(),
                old_state,
                new_state,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )

    def _expire_ignore(self, db: sqlite3.Connection, finding_id: str) -> None:
        row = self._row(db, finding_id)
        expiry = row["ignore_expiry"]
        if row["state"] != "IGNORED" or not expiry or date.fromisoformat(expiry) >= date.today():
            return
        db.execute(
            """UPDATE project_findings SET state='OPEN',ignore_reason=NULL,
               ignore_expiry=NULL,version=version+1 WHERE id=?""",
            (finding_id,),
        )
        self._audit(db, finding_id, "IGNORE_EXPIRED", "IGNORED", "OPEN")

    def upsert(self, project_id: str, occurrence: Any, assessment: Any, attempts: list[Any]) -> dict[str, Any] | None:
        now = _now()
        with self._db() as db:
            project = db.execute(
                "SELECT archived FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            if project["archived"]:
                raise ValueError("archived projects are read-only")
            row = db.execute(
                "SELECT * FROM project_findings WHERE project_id=? AND target_url=?",
                (project_id, occurrence.target_url),
            ).fetchone()
            if row is None:
                if assessment.classification != "CONFIRMED_BROKEN":
                    return None
                finding_id = uuid.uuid4().hex
                db.execute(
                    """INSERT INTO project_findings(
                        id,project_id,target_url,latest_status,classification,
                        reason,state,first_seen_at,last_seen_at,version
                    ) VALUES(?,?,?,?,?,?,'OPEN',?,?,1)""",
                    (
                        finding_id,
                        project_id,
                        occurrence.target_url,
                        attempts[-1].status,
                        assessment.classification,
                        assessment.reason,
                        now,
                        now,
                    ),
                )
                self._audit(db, finding_id, "CREATED", None, "OPEN")
            else:
                finding_id = row["id"]
                new_state = (
                    "OPEN"
                    if assessment.classification == "CONFIRMED_BROKEN"
                    and row["state"] == "RESOLVED"
                    else row["state"]
                )
                db.execute(
                    """UPDATE project_findings SET latest_status=?,classification=?,
                       reason=?,state=?,last_seen_at=?,version=version+1 WHERE id=?""",
                    (
                        attempts[-1].status,
                        assessment.classification,
                        assessment.reason,
                        new_state,
                        now,
                        finding_id,
                    ),
                )
                if new_state != row["state"]:
                    self._audit(
                        db, finding_id, "AUTO_REOPENED", row["state"], new_state
                    )
            anchor = occurrence.anchor_text[:500]
            context = occurrence.context[:500]
            fingerprint = hashlib.sha256(
                f"{anchor}\0{context}".encode("utf-8")
            ).hexdigest()
            db.execute(
                """INSERT INTO finding_occurrences VALUES(?,?,?,?,?,?,1,?,?)
                   ON CONFLICT(finding_id,source_url,fingerprint)
                   DO UPDATE SET active=1,last_seen_at=excluded.last_seen_at""",
                (
                    uuid.uuid4().hex,
                    finding_id,
                    occurrence.source_url,
                    anchor,
                    context,
                    fingerprint,
                    now,
                    now,
                ),
            )
            for sequence, attempt in enumerate(attempts):
                db.execute(
                    "INSERT INTO finding_evidence VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        finding_id,
                        now,
                        attempt.method,
                        attempt.status,
                        _sanitize_error(attempt.error),
                        attempt.latency_seconds,
                        sequence,
                        assessment.classification,
                        assessment.reason,
                    ),
                )
        return self.get(finding_id)

    def get(self, finding_id: str) -> dict[str, Any]:
        with self._db() as db:
            self._expire_ignore(db, finding_id)
            return dict(self._row(db, finding_id))

    def detail(self, finding_id: str) -> dict[str, Any]:
        with self._db() as db:
            self._expire_ignore(db, finding_id)
            item = dict(self._row(db, finding_id))
            item["occurrences"] = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM finding_occurrences WHERE finding_id=? ORDER BY source_url",
                    (finding_id,),
                )
            ]
            item["evidence"] = [
                dict(row)
                for row in db.execute(
                    """SELECT * FROM finding_evidence WHERE finding_id=?
                       ORDER BY observed_at DESC,sequence""",
                    (finding_id,),
                )
            ]
            item["verifications"] = [
                dict(row)
                for row in db.execute(
                    """SELECT * FROM finding_verifications WHERE finding_id=?
                       ORDER BY completed_at DESC""",
                    (finding_id,),
                )
            ]
            item["audit"] = [
                dict(row)
                for row in db.execute(
                    """SELECT * FROM finding_audit_events WHERE finding_id=?
                       ORDER BY created_at DESC""",
                    (finding_id,),
                )
            ]
            return item

    def list(
        self,
        project_id: str,
        state: str | None = None,
        classification: str | None = None,
        q: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if state and state not in STATES:
            raise ValueError("invalid finding state")
        if classification and classification not in CLASSIFICATIONS:
            raise ValueError("invalid classification")
        limit = max(1, min(100, int(limit)))
        offset = max(0, int(offset))
        with self._db() as db:
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM project_findings WHERE project_id=? AND state='IGNORED'",
                    (project_id,),
                )
            ]
            for finding_id in ids:
                self._expire_ignore(db, finding_id)
            where = ["pf.project_id=?"]
            args: list[Any] = [project_id]
            if state:
                where.append("pf.state=?")
                args.append(state)
            else:
                where.append("pf.state IN ('OPEN','ACKNOWLEDGED')")
            if classification:
                where.append("pf.classification=?")
                args.append(classification)
            if q:
                pattern = f"%{q}%"
                where.append(
                    """(pf.target_url LIKE ? OR COALESCE(pf.assignee,'') LIKE ? OR
                    EXISTS(SELECT 1 FROM finding_occurrences fo WHERE
                    fo.finding_id=pf.id AND (fo.source_url LIKE ? OR fo.anchor_text LIKE ?)))"""
                )
                args.extend([pattern, pattern, pattern, pattern])
            clause = " AND ".join(where)
            total = db.execute(
                f"SELECT count(*) FROM project_findings pf WHERE {clause}", args
            ).fetchone()[0]
            rows = db.execute(
                f"""SELECT pf.* FROM project_findings pf WHERE {clause}
                    ORDER BY pf.last_seen_at DESC,pf.id LIMIT ? OFFSET ?""",
                args + [limit, offset],
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _transition(
        self,
        finding_id: str,
        version: int,
        state: str,
        event: str,
        **fields: Any,
    ) -> dict[str, Any]:
        if state not in STATES:
            raise ValueError("invalid state")
        with self._db() as db:
            row = self._row(db, finding_id)
            project = db.execute(
                "SELECT archived FROM projects WHERE id=?", (row["project_id"],)
            ).fetchone()
            if project is None or project["archived"]:
                raise ValueError("archived or missing project is read-only")
            if row["version"] != version:
                raise VersionConflict("FINDING_VERSION_CONFLICT")
            values = {"state": state, "version": version + 1, **fields}
            assignments = ",".join(f"{key}=?" for key in values)
            db.execute(
                f"UPDATE project_findings SET {assignments} WHERE id=?",
                [*values.values(), finding_id],
            )
            self._audit(db, finding_id, event, row["state"], state, fields)
        return self.get(finding_id)

    def acknowledge(self, finding_id: str, version: int) -> dict[str, Any]:
        return self._transition(
            finding_id, version, "ACKNOWLEDGED", "ACKNOWLEDGED"
        )

    def assign(
        self, finding_id: str, version: int, assignee: str | None
    ) -> dict[str, Any]:
        value = (assignee or "").strip() or None
        if value and len(value) > 120:
            raise ValueError("assignee must be at most 120 characters")
        current = self.get(finding_id)
        return self._transition(
            finding_id, version, current["state"], "ASSIGNED", assignee=value
        )

    def ignore(
        self,
        finding_id: str,
        version: int,
        reason: str,
        expiry: str | None,
    ) -> dict[str, Any]:
        reason = reason.strip()
        if not reason or len(reason) > 500:
            raise ValueError("ignore reason must be 1 to 500 characters")
        if expiry:
            date.fromisoformat(expiry)
        return self._transition(
            finding_id,
            version,
            "IGNORED",
            "IGNORED",
            ignore_reason=reason,
            ignore_expiry=expiry,
        )

    def reopen(self, finding_id: str, version: int) -> dict[str, Any]:
        return self._transition(
            finding_id,
            version,
            "OPEN",
            "REOPENED",
            ignore_reason=None,
            ignore_expiry=None,
            resolved_at=None,
        )

    def reconcile_source(
        self, finding_id: str, source_url: str, present: bool
    ) -> None:
        """Mark source occurrences inactive only after a successful source fetch."""
        with self._db() as db:
            db.execute(
                "UPDATE finding_occurrences SET active=? WHERE finding_id=? AND source_url=?",
                (int(present), finding_id, source_url),
            )

    def record_verification(
        self,
        finding_id: str,
        version: int,
        outcome: str,
        checked: int,
        present: int,
        failures: list[dict[str, str]],
    ) -> dict[str, Any]:
        now = _now()
        with self._db() as db:
            row = self._row(db, finding_id)
            project = db.execute(
                "SELECT archived FROM projects WHERE id=?", (row["project_id"],)
            ).fetchone()
            if project is None or project["archived"]:
                raise ValueError("archived or missing project is read-only")
            if row["version"] != version:
                raise VersionConflict("FINDING_VERSION_CONFLICT")
            resolved = outcome in {"RECOVERED", "REMOVED_FROM_SOURCE"}
            state = "RESOLVED" if resolved else row["state"]
            db.execute(
                "INSERT INTO finding_verifications VALUES(?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    finding_id,
                    now,
                    outcome,
                    checked,
                    present,
                    json.dumps(failures),
                ),
            )
            db.execute(
                """UPDATE project_findings SET state=?,resolved_at=?,
                   latest_verification_at=?,latest_verification_outcome=?,
                   version=version+1 WHERE id=?""",
                (
                    state,
                    now if resolved else row["resolved_at"],
                    now,
                    outcome,
                    finding_id,
                ),
            )
            self._audit(
                db,
                finding_id,
                "VERIFIED",
                row["state"],
                state,
                {"outcome": outcome},
            )
        return self.get(finding_id)
