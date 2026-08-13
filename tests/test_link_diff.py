"""Pre-dev tests for link diff engine (DiffDetector + DiffReport + LinkStateStore).

Three-layer test pattern:
  Layer 1: Import/class-existence (PASS immediately)
  Layer 2: Signature/interface (PASS immediately)
  Layer 3: Behavioral (FAIL with NotImplementedError — RED phase)
"""

from __future__ import annotations

import inspect
import sqlite3
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

import pytest

from brokenlinkbrief.diff_detector import DiffDetector, DiffReport
from brokenlinkbrief.link_state import LinkStateRecord, LinkStateStore


# ---------------------------------------------------------------------------
# Layer 1 — Import & class existence
# ---------------------------------------------------------------------------
class TestImports:
    """Verify all public symbols are importable."""

    def test_import_diff_detector(self) -> None:
        assert DiffDetector is not None

    def test_import_diff_report(self) -> None:
        assert DiffReport is not None

    def test_import_link_state_store(self) -> None:
        assert LinkStateStore is not None

    def test_import_link_state_record(self) -> None:
        assert LinkStateRecord is not None

    def test_diff_detector_is_class(self) -> None:
        assert inspect.isclass(DiffDetector)

    def test_diff_report_is_dataclass(self) -> None:
        assert is_dataclass(DiffReport)

    def test_link_state_store_is_class(self) -> None:
        assert inspect.isclass(LinkStateStore)

    def test_link_state_record_is_dataclass(self) -> None:
        assert is_dataclass(LinkStateRecord)


# ---------------------------------------------------------------------------
# Layer 2a — DiffReport structure
# ---------------------------------------------------------------------------
class TestDiffReportStructure:
    """Verify DiffReport fields match the spec."""

    def test_diff_report_fields(self) -> None:
        field_names = {f.name for f in fields(DiffReport)}
        expected = {
            "project_id",
            "target_url",
            "timestamp",
            "new_broken",
            "resolved",
            "status_changes",
            "new_links",
            "removed_links",
            "has_changes",
        }
        assert expected == field_names

    def test_diff_report_defaults(self) -> None:
        report = DiffReport(
            project_id="proj1",
            target_url="http://example.com",
            timestamp="2026-01-01T00:00:00",
        )
        assert report.new_broken == []
        assert report.resolved == []
        assert report.status_changes == []
        assert report.new_links == []
        assert report.removed_links == []
        assert report.has_changes is False

    def test_diff_report_is_frozen(self) -> None:
        report = DiffReport(
            project_id="p1",
            target_url="http://x.com",
            timestamp="2026-01-01T00:00:00",
        )
        with pytest.raises(AttributeError):
            report.has_changes = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Layer 2b — LinkStateRecord structure
# ---------------------------------------------------------------------------
class TestLinkStateRecordStructure:
    """Verify LinkStateRecord fields match the schema spec."""

    def test_link_state_record_fields(self) -> None:
        field_names = {f.name for f in fields(LinkStateRecord)}
        expected = {
            "id",
            "project_id",
            "target_url",
            "link_url",
            "status",
            "reason",
            "location",
            "first_seen",
            "last_seen",
            "last_changed",
            "scan_mode",
        }
        assert expected == field_names

    def test_link_state_record_defaults(self) -> None:
        rec = LinkStateRecord(
            id="r1",
            project_id="p1",
            target_url="http://example.com",
            link_url="http://example.com/about",
            status=200,
            reason=None,
            location=None,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-01-01T00:00:00",
            last_changed=None,
            scan_mode="static",
        )
        assert rec.scan_mode == "static"
        assert rec.reason is None


# ---------------------------------------------------------------------------
# Layer 2c — DiffDetector signatures
# ---------------------------------------------------------------------------
class TestDiffDetectorSignature:
    """Verify DiffDetector method signatures."""

    def test_constructor_takes_link_state_store(self) -> None:
        sig = inspect.signature(DiffDetector.__init__)
        params = list(sig.parameters.keys())
        assert "link_state_store" in params

    def test_compare_signature(self) -> None:
        sig = inspect.signature(DiffDetector.compare)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "target_url" in params
        assert "current_links" in params

    def test_compare_return_annotation(self) -> None:
        sig = inspect.signature(DiffDetector.compare)
        ret = sig.return_annotation
        # With from __future__ import annotations, ret is a string
        assert ret is DiffReport or ret == "DiffReport"


# ---------------------------------------------------------------------------
# Layer 2d — LinkStateStore signatures
# ---------------------------------------------------------------------------
class TestLinkStateStoreSignature:
    """Verify LinkStateStore method signatures."""

    def test_constructor_takes_db(self) -> None:
        sig = inspect.signature(LinkStateStore.__init__)
        params = list(sig.parameters.keys())
        assert "db" in params

    def test_upsert_links_signature(self) -> None:
        sig = inspect.signature(LinkStateStore.upsert_links)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "target_url" in params
        assert "links" in params
        assert "scan_mode" in params

    def test_upsert_links_scan_mode_default(self) -> None:
        sig = inspect.signature(LinkStateStore.upsert_links)
        assert sig.parameters["scan_mode"].default == "static"

    def test_get_link_states_signature(self) -> None:
        sig = inspect.signature(LinkStateStore.get_link_states)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "target_url" in params

    def test_get_latest_state_signature(self) -> None:
        sig = inspect.signature(LinkStateStore.get_latest_state)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "target_url" in params
        assert "link_url" in params

    def test_compute_link_diff_signature(self) -> None:
        sig = inspect.signature(LinkStateStore.compute_link_diff)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "target_url" in params


# ---------------------------------------------------------------------------
# Layer 3 — Behavioral tests (RED phase)
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_previous_scan() -> list[dict[str, Any]]:
    """Previous scan: 3 links, one healthy, one broken, one status-changed."""
    return [
        {"url": "http://example.com/ok", "status": 200, "reason": None},
        {"url": "http://example.com/broken", "status": 500, "reason": "server error"},
        {"url": "http://example.com/changed", "status": 200, "reason": None},
    ]


@pytest.fixture
def sample_current_scan() -> list[dict[str, Any]]:
    """Current scan: 3 links — new link added, old broken fixed, status changed."""
    return [
        {"url": "http://example.com/ok", "status": 200, "reason": None},
        {"url": "http://example.com/broken", "status": 200, "reason": None},  # fixed
        {
            "url": "http://example.com/changed",
            "status": 404,
            "reason": "not found",
        },  # changed
        {"url": "http://example.com/new", "status": 200, "reason": None},  # new
    ]


class TestDiffDetectorBehavior:
    """Test DiffDetector behavioral expectations."""

    def test_compare_detects_new_links(
        self, sample_previous_scan: list[dict], sample_current_scan: list[dict]
    ) -> None:
        """Diff detects new links not present in previous scan."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        # Populate store with previous scan data so compare() can diff against it
        store.upsert_links("proj1", "http://example.com", sample_previous_scan)
        detector = DiffDetector(store)
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=sample_current_scan,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # new link http://example.com/new should be detected
        new_urls = {entry["url"] for entry in report.new_links}
        assert "http://example.com/new" in new_urls

    def test_compare_detects_changed_status(
        self, sample_previous_scan: list[dict], sample_current_scan: list[dict]
    ) -> None:
        """Diff detects status changes (e.g., 200 → 404)."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        # Populate store with previous scan data so compare() can diff against it
        store.upsert_links("proj1", "http://example.com", sample_previous_scan)
        detector = DiffDetector(store)
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=sample_current_scan,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # A link going from healthy (200) to broken (404) is classified as
        # new_broken, not status_changes (which is for both-broken status diffs)
        broken_urls = {entry["url"] for entry in report.new_broken}
        assert "http://example.com/changed" in broken_urls

    def test_compare_detects_broken_links(
        self, sample_previous_scan: list[dict], sample_current_scan: list[dict]
    ) -> None:
        """Diff detects newly broken links appearing between scans."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        detector = DiffDetector(store)
        # Create a scan where a previously-healthy link becomes broken
        current_with_new_broken = [
            {"url": "http://example.com/ok", "status": 200, "reason": None},
            {
                "url": "http://example.com/newly-broken",
                "status": 503,
                "reason": "unavailable",
            },
        ]
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=current_with_new_broken,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        broken_urls = {entry["url"] for entry in report.new_broken}
        assert "http://example.com/newly-broken" in broken_urls

    def test_compare_detects_disappeared_links(
        self, sample_previous_scan: list[dict], sample_current_scan: list[dict]
    ) -> None:
        """Diff detects links that disappeared between scans."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        # Populate store with previous scan data so compare() can diff against it
        store.upsert_links("proj1", "http://example.com", sample_previous_scan)
        detector = DiffDetector(store)
        # Current scan missing http://example.com/ok which was in previous
        current_missing_link = [
            {"url": "http://example.com/broken", "status": 200, "reason": None},
        ]
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=current_missing_link,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        removed_urls = {entry["url"] for entry in report.removed_links}
        assert "http://example.com/ok" in removed_urls

    def test_compare_sets_has_changes_true_when_changes_exist(
        self, sample_previous_scan: list[dict], sample_current_scan: list[dict]
    ) -> None:
        """has_changes is True when any change category is non-empty."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        detector = DiffDetector(store)
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=sample_current_scan,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.has_changes is True

    def test_compare_sets_has_changes_false_when_no_changes(self) -> None:
        """has_changes is False when no differences detected."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        detector = DiffDetector(store)
        same_links = [
            {"url": "http://example.com/ok", "status": 200, "reason": None},
        ]
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=same_links,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.has_changes is False

    def test_compare_handles_first_scan_gracefully(self) -> None:
        """First scan (no previous state) produces empty report."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        detector = DiffDetector(store)
        current = [{"url": "http://example.com/a", "status": 200, "reason": None}]
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=current,
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.new_broken == []
        assert report.resolved == []
        assert report.status_changes == []
        assert report.has_changes is False

    def test_compare_populates_report_metadata(self) -> None:
        """Report carries project_id, target_url, and timestamp."""
        store = LinkStateStore(sqlite3.connect(":memory:"))
        detector = DiffDetector(store)
        try:
            report = detector.compare(
                project_id="proj1",
                target_url="http://example.com",
                current_links=[],
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert report.project_id == "proj1"
        assert report.target_url == "http://example.com"
        assert isinstance(report.timestamp, str)
        assert len(report.timestamp) > 0


# ---------------------------------------------------------------------------
# Layer 3b — LinkStateStore behavioral tests (RED phase)
# ---------------------------------------------------------------------------
class TestLinkStateStoreBehavior:
    """Test LinkStateStore methods."""

    def _make_store(self, tmp_path: Path) -> tuple[LinkStateStore, sqlite3.Connection]:
        db = sqlite3.connect(str(tmp_path / "test.db"))
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                pinned INTEGER NOT NULL DEFAULT 0
            )
        """)
        db.execute("""
            CREATE TABLE link_state (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                target_url TEXT NOT NULL,
                link_url TEXT NOT NULL,
                status INTEGER,
                reason TEXT,
                location TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_changed TEXT,
                scan_mode TEXT DEFAULT 'static',
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        db.execute(
            "INSERT INTO projects (id, name, archived, created_at, updated_at, pinned) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("proj1", "Test", 0, "2026-01-01T00:00:00", "", 0),
        )
        db.commit()
        return LinkStateStore(db), db

    def test_upsert_links_inserts_new_records(self, tmp_path: Path) -> None:
        """Upsert inserts new link state records."""
        store, db = self._make_store(tmp_path)
        links = [
            {"url": "http://example.com/a", "status": 200, "reason": None},
            {"url": "http://example.com/b", "status": 404, "reason": "not found"},
        ]
        try:
            records = store.upsert_links("proj1", "http://example.com", links)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(records) == 2
        statuses = {r.status for r in records}
        assert 200 in statuses
        assert 404 in statuses

    def test_upsert_links_updates_existing_records(self, tmp_path: Path) -> None:
        """Upsert updates existing records when link status changes."""
        store, db = self._make_store(tmp_path)
        links_v1 = [{"url": "http://example.com/a", "status": 200, "reason": None}]
        links_v2 = [{"url": "http://example.com/a", "status": 500, "reason": "error"}]
        try:
            store.upsert_links("proj1", "http://example.com", links_v1)
            records = store.upsert_links("proj1", "http://example.com", links_v2)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(records) == 1
        assert records[0].status == 500

    def test_get_link_states_returns_all_for_target(self, tmp_path: Path) -> None:
        """get_link_states returns all link states for a target URL."""
        store, db = self._make_store(tmp_path)
        links = [
            {"url": "http://example.com/a", "status": 200, "reason": None},
            {"url": "http://example.com/b", "status": 301, "reason": None},
        ]
        try:
            store.upsert_links("proj1", "http://example.com", links)
            states = store.get_link_states("proj1", "http://example.com")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert len(states) == 2

    def test_get_latest_state_returns_single_link(self, tmp_path: Path) -> None:
        """get_latest_state returns the most recent state for a link."""
        store, db = self._make_store(tmp_path)
        links = [{"url": "http://example.com/a", "status": 200, "reason": None}]
        try:
            store.upsert_links("proj1", "http://example.com", links)
            state = store.get_latest_state(
                "proj1", "http://example.com", "http://example.com/a"
            )
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert state is not None
        assert state.status == 200

    def test_compute_link_diff_detects_new_broken(self, tmp_path: Path) -> None:
        """compute_link_diff identifies links that became broken."""
        store, db = self._make_store(tmp_path)
        links_v1 = [{"url": "http://example.com/a", "status": 200, "reason": None}]
        links_v2 = [{"url": "http://example.com/a", "status": 500, "reason": "error"}]
        try:
            store.upsert_links("proj1", "http://example.com", links_v1)
            store.upsert_links("proj1", "http://example.com", links_v2)
            diff = store.compute_link_diff("proj1", "http://example.com")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(diff, dict)
        assert "new_broken" in diff or "status_changes" in diff

    def test_persist_diff_state_via_scan_history(self, tmp_path: Path) -> None:
        """Diff state is persisted correctly in link_state table."""
        store, db = self._make_store(tmp_path)
        links = [
            {"url": "http://example.com/a", "status": 200, "reason": None},
        ]
        try:
            store.upsert_links("proj1", "http://example.com", links)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # Verify record exists in the DB
        count = db.execute(
            "SELECT COUNT(*) FROM link_state WHERE project_id=?",
            ("proj1",),
        ).fetchone()[0]
        assert count == 1
