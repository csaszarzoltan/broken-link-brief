"""Project-scoped cache for safe, policy-specific scan observations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .projects import configured_project_db

_ELIGIBLE = {"RECOVERED", "CONFIRMED_BROKEN"}
_MAX_TTL_SECONDS = 86400


class ObservationCache:
    """Persistent cache of scan observations keyed by project/url/fingerprint."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or configured_project_db())
        self._migrate()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def _migrate(self) -> None:
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS scan_observation_cache ("
                "id TEXT PRIMARY KEY,project_id TEXT NOT NULL,url TEXT NOT NULL,"
                "fingerprint TEXT NOT NULL,payload_json TEXT NOT NULL,"
                "classification TEXT NOT NULL,created_at TEXT NOT NULL,"
                "expires_at TEXT NOT NULL,UNIQUE(project_id,url,fingerprint))"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_observation_cache_expiry "
                "ON scan_observation_cache(expires_at)"
            )

    def put(
        self,
        project_id: str,
        url: str,
        fingerprint: str,
        payload: object,
        ttl_seconds: int,
        classification: str,
    ) -> bool:
        """Store a payload until it expires; returns False when not eligible."""
        if ttl_seconds <= 0 or classification not in _ELIGIBLE:
            return False
        now = datetime.now(timezone.utc)
        expires = (
            now + timedelta(seconds=min(ttl_seconds, _MAX_TTL_SECONDS))
        ).isoformat()
        with self._db() as db:
            db.execute(
                "DELETE FROM scan_observation_cache WHERE expires_at<=?",
                (now.isoformat(),),
            )
            db.execute(
                "INSERT OR REPLACE INTO scan_observation_cache "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    project_id,
                    url,
                    fingerprint,
                    json.dumps(payload, sort_keys=True),
                    classification,
                    now.isoformat(),
                    expires,
                ),
            )
        return True

    def get(self, project_id: str, url: str, fingerprint: str) -> object | None:
        """Return the cached payload for a key, or None when missing/expired."""
        stamp = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            row = db.execute(
                "SELECT payload_json FROM scan_observation_cache "
                "WHERE project_id=? AND url=? AND fingerprint=? AND expires_at>?",
                (project_id, url, fingerprint, stamp),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None
