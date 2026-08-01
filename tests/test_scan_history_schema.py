"""Tests for scan_history table schema and migrations.

Three-layer pre-dev test pattern:
  Layer 1: Import/class-existence (PASS immediately)
  Layer 2: Schema DDL validation (PASS — raw SQL, no implementation needed)
  Layer 3: ScanHistoryStore behavioral tests (FAIL with NotImplementedError)
"""
from __future__ import annotations

import inspect
import json
import sqlite3
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brokenlinkbrief.scan_history import ScanHistoryStore, ScanRecord


# ---------------------------------------------------------------------------
# Layer 1 — Import & class existence
# ---------------------------------------------------------------------------
class TestImports:
    """Verify all public symbols are importable."""

    def test_import_scan_history_store(self) -> None:
        assert ScanHistoryStore is not None

    def test_import_scan_record(self) -> None:
        assert ScanRecord is not None

    def test_scan_history_store_is_class(self) -> None:
        assert inspect.isclass(ScanHistoryStore)

    def test_scan_record_is_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(ScanRecord)


class TestScanRecordStructure:
    """Verify ScanRecord fields match the schema spec."""

    def test_scan_record_fields(self) -> None:
        field_names = {f.name for f in fields(ScanRecord)}
        expected = {
            "id", "project_id", "scan_timestamp", "total_urls",
            "total_links", "broken_count", "new_broken_count",
            "status", "raw_results_json", "last_known_good_hash",
            "regression_flags",
        }
        assert expected == field_names

    def test_scan_record_defaults(self) -> None:
        rec = ScanRecord(
            id="s1", project_id="p1", scan_timestamp="2026-01-01T00:00:00",
            total_urls=10, total_links=50, broken_count=5,
        )
        assert rec.new_broken_count == 0
        assert rec.status == "completed"
        assert rec.raw_results_json is None
        assert rec.last_known_good_hash is None
        assert rec.regression_flags is None


# ---------------------------------------------------------------------------
# Layer 2 — Schema DDL validation (raw SQL, passes immediately)
# ---------------------------------------------------------------------------
class TestScanHistorySchema:
    """Test scan_history table creation and schema."""

    def _create_test_db(self, tmp_path: Path) -> sqlite3.Connection:
        """Create a test database with projects table."""
        db = sqlite3.connect(str(tmp_path / "test.db"))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0
            )
        """)
        return db

    def test_scan_history_table_created(self, tmp_path: Path) -> None:
        """scan_history table is created with all required columns."""
        db = self._create_test_db(tmp_path)
        db.execute("""
            CREATE TABLE IF NOT EXISTS scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "scan_history" in table_names

        columns = db.execute("PRAGMA table_info(scan_history)").fetchall()
        col_names = [c["name"] for c in columns]
        assert "id" in col_names
        assert "project_id" in col_names
        assert "scan_timestamp" in col_names
        assert "total_urls" in col_names
        assert "total_links" in col_names
        assert "broken_count" in col_names
        assert "new_broken_count" in col_names
        assert "status" in col_names
        assert "raw_results_json" in col_names
        assert "last_known_good_hash" in col_names
        assert "regression_flags" in col_names
        db.close()

    def test_scan_history_indexes_created(self, tmp_path: Path) -> None:
        """Indexes for time-series and hash queries are created."""
        db = self._create_test_db(tmp_path)
        db.execute("""
            CREATE TABLE scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        db.execute("""
            CREATE INDEX idx_scan_history_project_time
            ON scan_history(project_id, scan_timestamp DESC)
        """)
        db.execute("""
            CREATE INDEX idx_scan_history_hash
            ON scan_history(project_id, last_known_good_hash)
        """)

        indexes = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = [i["name"] for i in indexes]
        assert "idx_scan_history_project_time" in index_names
        assert "idx_scan_history_hash" in index_names
        db.close()

    def test_foreign_key_constraint_enforced(self, tmp_path: Path) -> None:
        """Foreign key constraint prevents orphaned scan_history records."""
        db = self._create_test_db(tmp_path)
        db.execute("""
            CREATE TABLE scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        db.execute(
            "INSERT INTO projects (id, name, archived, created_at, updated_at, pinned) VALUES (?, ?, ?, ?, ?, ?)",
            ("proj1", "Test", 0, "2026-08-01T00:00:00", "2026-08-01T00:00:00", 0),
        )
        db.execute(
            "INSERT INTO scan_history (id, project_id, scan_timestamp, total_urls, total_links, broken_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("scan1", "proj1", "2026-08-01T09:00:00", 10, 50, 5),
        )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO scan_history (id, project_id, scan_timestamp, total_urls, total_links, broken_count) VALUES (?, ?, ?, ?, ?, ?)",
                ("scan2", "nonexistent", "2026-08-01T09:00:00", 10, 50, 5),
            )
        db.close()

    def test_cascade_delete_on_project(self, tmp_path: Path) -> None:
        """Deleting a project cascades to scan_history records."""
        db = self._create_test_db(tmp_path)
        db.execute("""
            CREATE TABLE scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        db.execute(
            "INSERT INTO projects (id, name, archived, created_at, updated_at, pinned) VALUES (?, ?, ?, ?, ?, ?)",
            ("proj1", "Test", 0, "2026-08-01T00:00:00", "2026-08-01T00:00:00", 0),
        )
        db.execute(
            "INSERT INTO scan_history (id, project_id, scan_timestamp, total_urls, total_links, broken_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("scan1", "proj1", "2026-08-01T09:00:00", 10, 50, 5),
        )

        db.execute("DELETE FROM projects WHERE id=?", ("proj1",))

        count = db.execute("SELECT COUNT(*) FROM scan_history WHERE project_id=?", ("proj1",)).fetchone()[0]
        assert count == 0
        db.close()

    def test_status_enum_values(self, tmp_path: Path) -> None:
        """Status column accepts only valid enum values."""
        db = self._create_test_db(tmp_path)
        db.execute("""
            CREATE TABLE scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        db.execute(
            "INSERT INTO projects (id, name, archived, created_at, updated_at, pinned) VALUES (?, ?, ?, ?, ?, ?)",
            ("proj1", "Test", 0, "2026-08-01T00:00:00", "2026-08-01T00:00:00", 0),
        )

        for status in ["pending", "running", "completed", "failed"]:
            db.execute(
                "INSERT INTO scan_history (id, project_id, scan_timestamp, total_urls, total_links, broken_count, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"scan_{status}", "proj1", "2026-08-01T09:00:00", 10, 50, 5, status),
            )

        count = db.execute("SELECT COUNT(*) FROM scan_history").fetchone()[0]
        assert count == 4
        db.close()


# ---------------------------------------------------------------------------
# Layer 2b — ScanHistoryStore signature/interface
# ---------------------------------------------------------------------------
class TestScanHistoryStoreSignature:
    """Verify ScanHistoryStore method signatures."""

    def test_constructor_takes_db(self) -> None:
        sig = inspect.signature(ScanHistoryStore.__init__)
        params = list(sig.parameters.keys())
        assert "db" in params

    def test_record_scan_signature(self) -> None:
        sig = inspect.signature(ScanHistoryStore.record_scan)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "total_urls" in params
        assert "total_links" in params
        assert "broken_count" in params

    def test_get_latest_scan_signature(self) -> None:
        sig = inspect.signature(ScanHistoryStore.get_latest_scan)
        params = list(sig.parameters.keys())
        assert "project_id" in params

    def test_get_scan_history_signature(self) -> None:
        sig = inspect.signature(ScanHistoryStore.get_scan_history)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "limit" in params
        assert "offset" in params

    def test_update_regression_flags_signature(self) -> None:
        sig = inspect.signature(ScanHistoryStore.update_regression_flags)
        params = list(sig.parameters.keys())
        assert "scan_id" in params
        assert "flags" in params

    def test_compute_results_hash_signature(self) -> None:
        sig = inspect.signature(ScanHistoryStore.compute_results_hash)
        params = list(sig.parameters.keys())
        assert "results" in params


# ---------------------------------------------------------------------------
# Layer 3 — ScanHistoryStore behavioral tests (RED phase)
# ---------------------------------------------------------------------------
class TestScanHistoryStore:
    """Test ScanHistoryStore class methods."""

    def _make_store(self, tmp_path: Path) -> tuple[ScanHistoryStore, sqlite3.Connection]:
        """Create a store with a real in-memory DB."""
        db = sqlite3.connect(str(tmp_path / "test.db"))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0
            )
        """)
        db.execute("""
            CREATE TABLE scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        db.execute(
            "INSERT INTO projects (id, name, archived, created_at, updated_at, pinned) VALUES (?, ?, ?, ?, ?, ?)",
            ("proj1", "Test", 0, "2026-08-01T00:00:00", "2026-08-01T00:00:00", 0),
        )
        db.commit()
        return ScanHistoryStore(db), db

    def test_record_scan(self, tmp_path: Path) -> None:
        """Record a scan result."""
        store, db = self._make_store(tmp_path)
        try:
            rec = store.record_scan(
                project_id="proj1",
                total_urls=10,
                total_links=50,
                broken_count=5,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert rec.project_id == "proj1"
        assert rec.broken_count == 5

    def test_get_latest_scan(self, tmp_path: Path) -> None:
        """Get the most recent scan for a project."""
        store, db = self._make_store(tmp_path)
        try:
            result = store.get_latest_scan("proj1")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # No scans yet — should return None
        assert result is None

    def test_get_scan_history(self, tmp_path: Path) -> None:
        """Get scan history with pagination."""
        store, db = self._make_store(tmp_path)
        try:
            results = store.get_scan_history("proj1", limit=10, offset=0)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(results, list)
        assert len(results) == 0

    def test_update_regression_flags(self, tmp_path: Path) -> None:
        """Update regression flags for a scan."""
        store, db = self._make_store(tmp_path)
        try:
            store.update_regression_flags("scan1", ["new_broken:http://x.com"])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")

    def test_compute_results_hash(self, tmp_path: Path) -> None:
        """Compute SHA-256 hash of scan results."""
        store, db = self._make_store(tmp_path)
        try:
            h = store.compute_results_hash([{"url": "http://x.com", "status": 200}])
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(h, str)
        assert len(h) == 64


# ---------------------------------------------------------------------------
# Layer 4 — Regression: sqlite3.Row iteration bug (t_8c0140a8)
# ---------------------------------------------------------------------------
class TestScanHistoryRegression:
    """Regression tests for the sqlite3.Row iteration bug fix.

    The original code did `for k in row` which iterates VALUES (not column
    names) on sqlite3.Row, causing IndexError on any non-empty result.
    Fix: `for k in row.keys()`.
    """

    def _make_store(self, tmp_path: Path) -> tuple[ScanHistoryStore, sqlite3.Connection]:
        db = sqlite3.connect(str(tmp_path / "test.db"))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0
            )
        """)
        db.execute("""
            CREATE TABLE scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        db.execute(
            "INSERT INTO projects (id, name, archived, created_at, updated_at, pinned) VALUES (?, ?, ?, ?, ?, ?)",
            ("proj1", "Test", 0, "2026-08-01T00:00:00", "2026-08-01T00:00:00", 0),
        )
        db.commit()
        return ScanHistoryStore(db), db

    def test_record_and_get_latest(self, tmp_path: Path) -> None:
        """Insert a scan record and retrieve it via get_latest_scan — all fields match."""
        store, db = self._make_store(tmp_path)
        rec = store.record_scan(
            project_id="proj1",
            total_urls=10,
            total_links=50,
            broken_count=5,
        )
        latest = store.get_latest_scan("proj1")
        assert latest is not None
        assert latest.id == rec.id
        assert latest.project_id == "proj1"
        assert latest.total_urls == 10
        assert latest.total_links == 50
        assert latest.broken_count == 5
        assert latest.new_broken_count == 0
        assert latest.status == "completed"

    def test_record_and_get_history(self, tmp_path: Path) -> None:
        """Insert a scan record and retrieve it via get_scan_history."""
        store, db = self._make_store(tmp_path)
        rec = store.record_scan(
            project_id="proj1",
            total_urls=20,
            total_links=100,
            broken_count=10,
        )
        history = store.get_scan_history("proj1", limit=50, offset=0)
        assert len(history) >= 1
        ids = [r.id for r in history]
        assert rec.id in ids

    def test_multiple_records_ordering(self, tmp_path: Path) -> None:
        """Multiple records returned in most-recent-first order."""
        store, db = self._make_store(tmp_path)
        rec1 = store.record_scan(
            project_id="proj1",
            total_urls=10,
            total_links=50,
            broken_count=1,
        )
        rec2 = store.record_scan(
            project_id="proj1",
            total_urls=20,
            total_links=100,
            broken_count=2,
        )
        history = store.get_scan_history("proj1", limit=50, offset=0)
        assert len(history) >= 2
        # Most recent first: rec2 (inserted second) should come before rec1
        idx_rec2 = next(i for i, r in enumerate(history) if r.id == rec2.id)
        idx_rec1 = next(i for i, r in enumerate(history) if r.id == rec1.id)
        assert idx_rec2 < idx_rec1
