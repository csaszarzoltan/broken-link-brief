"""Per-URL link state tracking for diff computation.

Stores individual link states in SQLite with upsert support,
enabling per-URL diff computation between scans.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LinkStateRecord:
    """A single link state record."""

    id: str
    project_id: str
    target_url: str
    link_url: str
    status: int | None
    reason: str | None
    location: str | None
    first_seen: str
    last_seen: str
    last_changed: str | None
    scan_mode: str  # 'static' | 'spa'


class LinkStateStore:
    """SQLite-backed per-URL link state storage."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the link_state table if it does not exist."""
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS link_state ("
            "id TEXT PRIMARY KEY,"
            "project_id TEXT NOT NULL,"
            "target_url TEXT NOT NULL,"
            "link_url TEXT NOT NULL,"
            "status INTEGER,"
            "reason TEXT,"
            "location TEXT,"
            "first_seen TEXT NOT NULL,"
            "last_seen TEXT NOT NULL,"
            "last_changed TEXT,"
            "scan_mode TEXT DEFAULT 'static',"
            "FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE"
            ")"
        )

    def upsert_links(
        self,
        project_id: str,
        target_url: str,
        links: list[dict[str, Any]],
        scan_mode: str = "static",
    ) -> list[LinkStateRecord]:
        """Upsert link records for a scan. Returns created/updated records."""
        now = datetime.now(timezone.utc).isoformat()
        records: list[LinkStateRecord] = []

        for link in links:
            link_url = link["url"]
            status = link.get("status")
            reason = link.get("reason")
            location = link.get("location")

            # Check if a record already exists for this link
            existing = self._db.execute(
                "SELECT id, status, first_seen FROM link_state "
                "WHERE project_id=? AND target_url=? AND link_url=? "
                "ORDER BY last_seen DESC LIMIT 1",
                (project_id, target_url, link_url),
            ).fetchone()

            if existing is not None:
                # Handle both sqlite3.Row and tuple
                if hasattr(existing, "keys"):
                    rec_id = existing["id"]
                    prev_status = existing["status"]
                    original_first_seen = existing["first_seen"]
                else:
                    rec_id = existing[0]
                    prev_status = existing[1]
                    original_first_seen = existing[2]
                last_changed = now if status != prev_status else None
                self._db.execute(
                    "UPDATE link_state SET status=?, reason=?, location=?, "
                    "last_seen=?, last_changed=?, scan_mode=? WHERE id=?",
                    (status, reason, location, now, last_changed, scan_mode, rec_id),
                )
                record = LinkStateRecord(
                    id=rec_id,
                    project_id=project_id,
                    target_url=target_url,
                    link_url=link_url,
                    status=status,
                    reason=reason,
                    location=location,
                    first_seen=original_first_seen,
                    last_seen=now,
                    last_changed=last_changed,
                    scan_mode=scan_mode,
                )
            else:
                rec_id = uuid.uuid4().hex
                self._db.execute(
                    "INSERT INTO link_state "
                    "(id, project_id, target_url, link_url, status, reason, "
                    "location, first_seen, last_seen, last_changed, scan_mode) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rec_id,
                        project_id,
                        target_url,
                        link_url,
                        status,
                        reason,
                        location,
                        now,
                        now,
                        None,
                        scan_mode,
                    ),
                )
                record = LinkStateRecord(
                    id=rec_id,
                    project_id=project_id,
                    target_url=target_url,
                    link_url=link_url,
                    status=status,
                    reason=reason,
                    location=location,
                    first_seen=now,
                    last_seen=now,
                    last_changed=None,
                    scan_mode=scan_mode,
                )
            records.append(record)

        self._db.commit()
        return records

    def _row_to_record(self, row: Any) -> LinkStateRecord:
        """Convert a DB row to a LinkStateRecord, handling both Row and tuple."""
        if hasattr(row, "keys"):
            return LinkStateRecord(
                id=row["id"],
                project_id=row["project_id"],
                target_url=row["target_url"],
                link_url=row["link_url"],
                status=row["status"],
                reason=row["reason"],
                location=row["location"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                last_changed=row["last_changed"],
                scan_mode=row["scan_mode"],
            )
        # tuple index fallback
        return LinkStateRecord(
            id=row[0],
            project_id=row[1],
            target_url=row[2],
            link_url=row[3],
            status=row[4],
            reason=row[5],
            location=row[6],
            first_seen=row[7],
            last_seen=row[8],
            last_changed=row[9],
            scan_mode=row[10],
        )

    def get_link_states(
        self, project_id: str, target_url: str
    ) -> list[LinkStateRecord]:
        """Get all link states for a target URL."""
        rows = self._db.execute(
            "SELECT * FROM link_state WHERE project_id=? AND target_url=? "
            "ORDER BY last_seen DESC",
            (project_id, target_url),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_latest_state(
        self, project_id: str, target_url: str, link_url: str
    ) -> LinkStateRecord | None:
        """Get the latest state for a specific link."""
        row = self._db.execute(
            "SELECT * FROM link_state "
            "WHERE project_id=? AND target_url=? AND link_url=? "
            "ORDER BY last_seen DESC LIMIT 1",
            (project_id, target_url, link_url),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def compute_link_diff(self, project_id: str, target_url: str) -> dict[str, Any]:
        """Compute diff of link states between consecutive scans.

        Returns a dict with ``new_broken`` and ``status_changes`` lists.
        """
        # Get all link states grouped by link_url
        all_states = self.get_link_states(project_id, target_url)
        by_link: dict[str, list[LinkStateRecord]] = {}
        for s in all_states:
            by_link.setdefault(s.link_url, []).append(s)

        new_broken: list[dict[str, Any]] = []
        status_changes: list[dict[str, Any]] = []

        for link_url, records in by_link.items():
            if len(records) < 2:
                continue

            # Sort by last_seen descending: records[0] is latest
            latest = records[0]
            previous = records[1]

            # Detect newly broken: previous was OK (status < 400), now broken
            prev_was_ok = previous.status is not None and previous.status < 400
            curr_is_broken = latest.status is not None and latest.status >= 400

            if prev_was_ok and curr_is_broken:
                entry: dict[str, Any] = {"url": link_url, "status": latest.status}
                if latest.reason:
                    entry["reason"] = latest.reason
                entry["previous_status"] = previous.status
                new_broken.append(entry)
            elif curr_is_broken and not prev_was_ok:
                # Both broken or previous was broken — check for status change
                if latest.status != previous.status:
                    status_changes.append(
                        {
                            "url": link_url,
                            "previous_status": previous.status,
                            "current_status": latest.status,
                        }
                    )

        return {"new_broken": new_broken, "status_changes": status_changes}
