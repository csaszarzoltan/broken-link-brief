"""Scan history storage and schema management."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScanRecord:
    """A single scan history record."""
    id: str
    project_id: str
    scan_timestamp: str
    total_urls: int
    total_links: int
    broken_count: int
    new_broken_count: int = 0
    status: str = "completed"
    raw_results_json: str | None = None
    last_known_good_hash: str | None = None
    regression_flags: str | None = None


class ScanHistoryStore:
    """SQLite-backed scan history storage."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def record_scan(
        self,
        project_id: str,
        total_urls: int,
        total_links: int,
        broken_count: int,
        raw_results: list[dict[str, Any]] | None = None,
        new_broken_count: int = 0,
        status: str = "completed",
        last_known_good_hash: str | None = None,
        regression_flags: list[str] | None = None,
    ) -> ScanRecord:
        """Record a scan result and return the created ScanRecord."""
        from datetime import datetime, timezone
        scan_id = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc).isoformat()
        raw_json = json.dumps(raw_results) if raw_results else None
        flags_json = json.dumps(regression_flags) if regression_flags else None
        self._db.execute(
            """INSERT INTO scan_history
            (id, project_id, scan_timestamp, total_urls, total_links,
             broken_count, new_broken_count, status, raw_results_json,
             last_known_good_hash, regression_flags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, project_id, timestamp, total_urls, total_links,
             broken_count, new_broken_count, status, raw_json,
             last_known_good_hash, flags_json),
        )
        self._db.commit()
        return ScanRecord(
            id=scan_id, project_id=project_id, scan_timestamp=timestamp,
            total_urls=total_urls, total_links=total_links,
            broken_count=broken_count, new_broken_count=new_broken_count,
            status=status, raw_results_json=raw_json,
            last_known_good_hash=last_known_good_hash,
            regression_flags=flags_json,
        )

    def get_latest_scan(self, project_id: str) -> ScanRecord | None:
        """Get the most recent scan for a project. Returns None if no scans exist."""
        row = self._db.execute(
            """SELECT * FROM scan_history WHERE project_id=?
            ORDER BY scan_timestamp DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return ScanRecord(**{k: row[k] for k in row})

    def get_scan_history(
        self, project_id: str, limit: int = 50, offset: int = 0
    ) -> list[ScanRecord]:
        """Get scan history with pagination."""
        rows = self._db.execute(
            """SELECT * FROM scan_history WHERE project_id=?
            ORDER BY scan_timestamp DESC LIMIT ? OFFSET ?""",
            (project_id, limit, offset),
        ).fetchall()
        return [ScanRecord(**{k: r[k] for k in r}) for r in rows]

    def update_regression_flags(self, scan_id: str, flags: list[str]) -> None:
        """Update regression flags for a scan."""
        flags_json = json.dumps(flags)
        self._db.execute(
            "UPDATE scan_history SET regression_flags=? WHERE id=?",
            (flags_json, scan_id),
        )
        self._db.commit()

    def compute_results_hash(self, results: list[dict[str, Any]]) -> str:
        """Compute SHA-256 hash of scan results."""
        canonical = json.dumps(results, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
