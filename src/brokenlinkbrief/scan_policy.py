"""Versioned project and exact-host scan policies."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .projects import configured_project_db

_ALLOWED = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ScanPolicy:
    """A validated scan policy with defaults for a project."""

    timeout_seconds: float = 10.0
    max_concurrency: int = 5
    max_attempts: int = 2
    backoff_seconds: float = 0.5
    respect_retry_after: bool = True
    cache_ttl_seconds: int = 0
    temporary_statuses: tuple[int, ...] = (408, 429, 500, 502, 503, 504)

    def validated(self) -> ScanPolicy:
        """Return a copy with all fields range-checked and normalized."""
        if not 1.0 <= self.timeout_seconds <= 60.0:
            raise ValueError("timeout_seconds must be between 1 and 60")
        if (
            isinstance(self.max_concurrency, bool)
            or not 1 <= self.max_concurrency <= 20
        ):
            raise ValueError("max_concurrency must be between 1 and 20")
        if isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if not 0 <= self.backoff_seconds <= 10:
            raise ValueError("backoff_seconds must be between 0 and 10")
        if not isinstance(self.respect_retry_after, bool):
            raise ValueError("respect_retry_after must be boolean")
        if (
            isinstance(self.cache_ttl_seconds, bool)
            or not 0 <= self.cache_ttl_seconds <= 86400
        ):
            raise ValueError("cache_ttl_seconds must be between 0 and 86400")
        statuses = tuple(sorted(set(self.temporary_statuses)))
        if not set(statuses) <= _ALLOWED:
            raise ValueError("temporary_statuses contains unsupported status")
        return replace(self, temporary_statuses=statuses)

    @property
    def fingerprint(self) -> str:
        """Stable fingerprint of the validated policy."""
        return hashlib.sha256(
            json.dumps(
                asdict(self.validated()),
                sort_keys=True,
                separators=(",", ":"),
                default=list,
            ).encode()
        ).hexdigest()


@dataclass(frozen=True)
class EffectivePolicy:
    """The resolved policy for a specific hostname."""

    policy: ScanPolicy
    version: int
    rule: str
    hostname: str

    @property
    def fingerprint(self) -> str:
        """Fingerprint of the resolved policy."""
        return self.policy.fingerprint


def _policy(data: dict) -> ScanPolicy:
    """Build and validate a ScanPolicy from a dict."""
    allowed = set(ScanPolicy.__dataclass_fields__)
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    if "temporary_statuses" in data:
        data = dict(data)
        data["temporary_statuses"] = tuple(data["temporary_statuses"])
    return ScanPolicy(**data).validated()


def _host(value: str) -> str:
    """Normalize a hostname to lowercase IDNA, requiring an exact DNS name."""
    if "://" in value:
        value = urlsplit(value).hostname or ""
    value = value.strip().rstrip(".").lower()
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("invalid hostname") from exc
    if not value or "/" in value or "*" in value or " " in value or "." not in value:
        raise ValueError("hostname must be an exact DNS hostname")
    return value


class PolicyConflict(ValueError):  # noqa: N818 — legacy public API name
    """Raised when a policy write races with another session."""


# Backwards-compatible alias (legacy name referenced by tests and callers).
PolicyConflictError = PolicyConflict


class ScanPolicyStore:
    """Persistent versioned scan policies with per-host overrides."""

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
            db.execute(
                "CREATE TABLE IF NOT EXISTS scan_policy_versions "
                "(id INTEGER PRIMARY KEY "
                "AUTOINCREMENT, project_id TEXT NOT NULL,"
                " version_number INTEGER NOT NULL, "
                "defaults_json TEXT NOT NULL, created_at TEXT NOT NULL, "
                "UNIQUE(project_id,version_number))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS scan_policy_host_overrides ("
                "policy_version_id INTEGER NOT NULL, hostname TEXT NOT NULL, "
                "override_json TEXT NOT NULL, "
                "PRIMARY KEY(policy_version_id,hostname), "
                "FOREIGN KEY(policy_version_id) "
                "REFERENCES scan_policy_versions(id) ON DELETE CASCADE)"
            )

    def get(self, project_id: str) -> dict:
        """Return the latest policy document for a project."""
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM scan_policy_versions WHERE project_id=? "
                "ORDER BY version_number DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if not row:
                return {
                    "version": 0,
                    "defaults": asdict(ScanPolicy()),
                    "host_overrides": [],
                    "created_at": None,
                }
            overrides = [
                {
                    "hostname": r["hostname"],
                    "overrides": json.loads(r["override_json"]),
                }
                for r in db.execute(
                    "SELECT * FROM scan_policy_host_overrides "
                    "WHERE policy_version_id=? ORDER BY hostname",
                    (row["id"],),
                )
            ]
            return {
                "version": row["version_number"],
                "defaults": json.loads(row["defaults_json"]),
                "host_overrides": overrides,
                "created_at": row["created_at"],
            }

    def save(
        self,
        project_id: str,
        expected_version: int,
        defaults: dict,
        host_overrides: list[dict],
    ) -> dict:
        """Save the next policy version, guarding against concurrent writes."""
        current = self.get(project_id)
        if current["version"] != expected_version:
            raise PolicyConflict("policy changed in another session")
        base = _policy(defaults)
        seen: set[str] = set()
        clean: list[tuple[str, dict]] = []
        for item in host_overrides:
            if set(item) != {"hostname", "overrides"}:
                raise ValueError("host override requires hostname and overrides")
            host = _host(str(item["hostname"]))
            if host in seen:
                raise ValueError("duplicate hostname override")
            seen.add(host)
            merged = asdict(base)
            merged.update(item["overrides"])
            _policy(merged)
            clean.append((host, item["overrides"]))
        version = expected_version + 1
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            if (
                db.execute(
                    "SELECT 1 FROM projects WHERE id=? AND archived=0",
                    (project_id,),
                ).fetchone()
                is None
            ):
                raise ValueError("active project is required")
            cur = db.execute(
                "INSERT INTO scan_policy_versions(project_id,version_number,"
                "defaults_json,created_at) VALUES (?,?,?,?)",
                (
                    project_id,
                    version,
                    json.dumps(asdict(base), sort_keys=True),
                    now,
                ),
            )
            db.executemany(
                "INSERT INTO scan_policy_host_overrides VALUES (?,?,?)",
                [
                    (cur.lastrowid, h, json.dumps(o, sort_keys=True))
                    for h, o in clean
                ],
            )
        return self.get(project_id)

    def resolve(
        self,
        project_id: str,
        url: str,
        draft: dict | None = None,
    ) -> EffectivePolicy:
        """Resolve the effective policy for a URL's hostname."""
        doc = draft or self.get(project_id)
        host = _host(urlsplit(url).hostname or "")
        base = _policy(doc["defaults"])
        rule = "PROJECT_DEFAULT"
        for item in doc.get("host_overrides", []):
            if _host(item["hostname"]) == host:
                data = asdict(base)
                data.update(item["overrides"])
                base = _policy(data)
                rule = "HOST_OVERRIDE"
                break
        return EffectivePolicy(base, int(doc.get("version", 0)), rule, host)
