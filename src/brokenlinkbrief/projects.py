"""Durable saved projects for repeat scanning workflows."""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_PROJECT_DB_ENV = "BROKENLINKBRIEF_PROJECT_DB"


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    targets: tuple[str, ...]
    archived: bool
    created_at: str
    updated_at: str
    pinned: bool = False


def configured_project_db() -> Path:
    """Return the configured project database path."""
    return Path(os.environ.get(_PROJECT_DB_ENV, ".brokenlinkbrief.db"))


def normalize_target(url: str) -> str:
    """Normalize a project target without performing network access."""
    value = url.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("target must be an absolute HTTP or HTTPS URL")
    hostname = parsed.hostname.lower()
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = hostname if port in {None, default_port} else f"{hostname}:{port}"
    if parsed.username or parsed.password:
        raise ValueError("target credentials are not allowed")
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


class ProjectStore:
    """SQLite persistence for named groups of scan targets."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or configured_project_db())
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                """CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0
                )"""
            )
            project_columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "pinned" not in project_columns:
                db.execute(
                    "ALTER TABLE projects ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
                )
            db.execute(
                """CREATE TABLE IF NOT EXISTS project_targets (
                    project_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    PRIMARY KEY(project_id, url),
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                        ON DELETE CASCADE
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create(self, name: str, targets: list[str]) -> Project:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("name is required")
        normalized = tuple(dict.fromkeys(normalize_target(item) for item in targets))
        if not normalized:
            raise ValueError("at least one target is required")
        if len(normalized) > 50:
            raise ValueError("maximum 50 targets per project")
        now = datetime.now(timezone.utc).isoformat()
        project_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute(
                "INSERT INTO projects "
                "(id, name, archived, created_at, updated_at, pinned) "
                "VALUES (?,?,?,?,?,?)",
                (project_id, clean_name, 0, now, now, 0),
            )
            db.executemany(
                "INSERT INTO project_targets VALUES (?,?,?)",
                [(project_id, index, url) for index, url in enumerate(normalized)],
            )
        return Project(project_id, clean_name, normalized, False, now, now, False)

    def get(self, project_id: str) -> Project:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if row is None:
                raise KeyError(project_id)
            targets = tuple(
                item["url"]
                for item in db.execute(
                    "SELECT url FROM project_targets WHERE project_id=? "
                    "ORDER BY position",
                    (project_id,),
                ).fetchall()
            )
        return Project(
            row["id"],
            row["name"],
            targets,
            bool(row["archived"]),
            row["created_at"],
            row["updated_at"],
            bool(row["pinned"]),
        )

    def _list_by_archived(self, archived: bool) -> list[Project]:
        with self._connect() as db:
            ids = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM projects WHERE archived=? "
                    "ORDER BY pinned DESC, updated_at DESC, name",
                    (int(archived),),
                ).fetchall()
            ]
        return [self.get(project_id) for project_id in ids]

    def list_active(self) -> list[Project]:
        return self._list_by_archived(False)

    def list_archived(self) -> list[Project]:
        return self._list_by_archived(True)

    def set_pinned(self, project_id: str, pinned: bool) -> Project:
        """Pin or unpin a project and return its updated representation."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE projects SET pinned=?, updated_at=? WHERE id=?",
                (int(pinned), now, project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
        return self.get(project_id)

    def duplicate(self, project_id: str) -> Project:
        """Create an active copy with a deterministic available name."""
        source = self.get(project_id)
        with self._connect() as db:
            names = {
                row["name"]
                for row in db.execute("SELECT name FROM projects").fetchall()
            }
        base = f"{source.name} copy"
        candidate = base
        suffix = 2
        while candidate in names:
            candidate = f"{base} {suffix}"
            suffix += 1
        return self.create(candidate, list(source.targets))

    def export_configuration(self, project_id: str) -> dict[str, object]:
        """Return a portable, versioned configuration without runtime state."""
        project = self.get(project_id)
        return {
            "schema_version": 1,
            "name": project.name,
            "targets": list(project.targets),
        }

    def import_configuration(self, payload: dict[str, object]) -> Project:
        """Create a new project from a supported portable configuration."""
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported project configuration schema")
        name = payload.get("name")
        targets = payload.get("targets")
        if not isinstance(name, str) or not isinstance(targets, list):
            raise ValueError("project configuration requires name and targets")
        if not all(isinstance(item, str) for item in targets):
            raise ValueError("project targets must be strings")
        return self.create(name, targets)

    def summarize(self, project: Project, history_store: object) -> dict[str, object]:
        """Aggregate the latest retained scan for every project target."""
        scanned_targets = 0
        total_links = 0
        broken_count = 0
        last_scan_timestamp: str | None = None
        for target in project.targets:
            records = history_store.get_history(target, limit=1)
            if not records:
                continue
            scanned_targets += 1
            record = records[0]
            timestamp = record.get("timestamp")
            if timestamp and (
                last_scan_timestamp is None or timestamp > last_scan_timestamp
            ):
                last_scan_timestamp = timestamp
            results = record.get("results", [])
            total_links += len(results)
            broken_count += sum(
                1
                for item in results
                if (item.get("status") is not None and item.get("status") >= 400)
                or (item.get("status") is None and item.get("reason") is not None)
            )
        return {
            "scanned_targets": scanned_targets,
            "unscanned_targets": len(project.targets) - scanned_targets,
            "total_links": total_links,
            "broken_count": broken_count,
            "last_scan_timestamp": last_scan_timestamp,
        }

    def update(self, project_id: str, name: str, targets: list[str]) -> Project:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("name is required")
        normalized = tuple(dict.fromkeys(normalize_target(item) for item in targets))
        if not normalized:
            raise ValueError("at least one target is required")
        if len(normalized) > 50:
            raise ValueError("maximum 50 targets per project")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            if (
                db.execute(
                    "SELECT 1 FROM projects WHERE id=?", (project_id,)
                ).fetchone()
                is None
            ):
                raise KeyError(project_id)
            db.execute(
                "UPDATE projects SET name=?, updated_at=? WHERE id=?",
                (clean_name, now, project_id),
            )
            db.execute("DELETE FROM project_targets WHERE project_id=?", (project_id,))
            db.executemany(
                "INSERT INTO project_targets VALUES (?,?,?)",
                [(project_id, index, url) for index, url in enumerate(normalized)],
            )
        return self.get(project_id)

    def restore(self, project_id: str) -> Project:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE projects SET archived=0, updated_at=? WHERE id=?",
                (now, project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
        return self.get(project_id)

    def archive(self, project_id: str) -> Project:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE projects SET archived=1, updated_at=? WHERE id=?",
                (now, project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
        return self.get(project_id)
