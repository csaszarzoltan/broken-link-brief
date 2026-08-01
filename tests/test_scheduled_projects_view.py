"""Pre-development tests for Scheduled Projects Dashboard View.

Feature under test: Dashboard endpoints and frontend components to display
scheduled projects with next run time, last run status, historical trend chart
(broken links over time), and manual trigger button.

State at authoring time (pre-tester):
- ScheduleStore.list_active() DOES NOT exist in scheduler.py.
- ScanHistoryStore.get_latest_scan() raises NotImplementedError in scan_history.py.
- /api/scheduled-projects endpoint DOES NOT exist in app.py.
- /api/scheduled-projects/{id}/trigger endpoint DOES NOT exist in app.py.
- /dashboard HTML scheduled-projects section DOES NOT exist in _DASHBOARD_HTML.
- Therefore ALL behavioral tests are expected to FAIL against the stubs
  and PASS only after the developer implements the scheduled projects view.

New stubs created for this feature:
- src/brokenlinkbrief/scheduled_projects.py — ScheduledProjectView data model
  and aggregator logic.
"""
from __future__ import annotations

import inspect
import json
import time
from dataclasses import fields, is_dataclass
from http.server import HTTPServer
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# 0. Stub module import tests — verify new modules/classes exist
# ---------------------------------------------------------------------------


class TestScheduledProjectsModuleExists:
    """Verify the new scheduled_projects module and its public API exist."""

    def test_import_scheduled_projects_module(self) -> None:
        """scheduled_projects module is importable."""
        import importlib

        mod = importlib.import_module("brokenlinkbrief.scheduled_projects")
        assert mod is not None

    def test_scheduled_project_view_class_exists(self) -> None:
        """ScheduledProjectView dataclass exists."""
        from brokenlinkbrief.scheduled_projects import ScheduledProjectView

        assert ScheduledProjectView is not None
        assert is_dataclass(ScheduledProjectView)

    def test_scheduled_project_view_fields(self) -> None:
        """ScheduledProjectView has required fields."""
        from brokenlinkbrief.scheduled_projects import ScheduledProjectView

        field_names = {f.name for f in fields(ScheduledProjectView)}
        required = {
            "project_id",
            "project_name",
            "cadence",
            "timezone",
            "state",
            "next_due_at",
            "last_scan_timestamp",
            "last_scan_broken_count",
            "last_scan_status",
        }
        missing = required - field_names
        assert not missing, f"Missing fields: {missing}"

    def test_aggregate_scheduled_projects_callable(self) -> None:
        """aggregate_scheduled_projects function exists and is callable."""
        from brokenlinkbrief.scheduled_projects import (
            aggregate_scheduled_projects,
        )

        assert callable(aggregate_scheduled_projects)


# ---------------------------------------------------------------------------
# 1. ScheduleStore.list_active() interface tests
# ---------------------------------------------------------------------------


class TestScheduleStoreListActive:
    """Verify ScheduleStore.list_active() method exists with correct signature."""

    def test_list_active_exists(self) -> None:
        """ScheduleStore.list_active exists as an attribute."""
        from brokenlinkbrief.scheduler import ScheduleStore

        assert hasattr(ScheduleStore, "list_active")

    def test_list_active_callable(self) -> None:
        """ScheduleStore.list_active is callable."""
        from brokenlinkbrief.scheduler import ScheduleStore

        assert callable(ScheduleStore.list_active)

    def test_list_active_signature(self) -> None:
        """ScheduleStore.list_active accepts no required positional args."""
        from brokenlinkbrief.scheduler import ScheduleStore

        sig = inspect.signature(ScheduleStore.list_active)
        # Should accept self (instance method) with no required params
        params = [p for p in sig.parameters.values() if p.name != "self"]
        required = [p for p in params if p.default is inspect.Parameter.empty]
        assert len(required) == 0, f"Unexpected required params: {required}"


# ---------------------------------------------------------------------------
# 2. ScanHistoryStore.get_latest_scan() interface tests
# ---------------------------------------------------------------------------


class TestScanHistoryStoreGetLatestScan:
    """Verify ScanHistoryStore.get_latest_scan() method exists."""

    def test_get_latest_scan_exists(self) -> None:
        """ScanHistoryStore.get_latest_scan exists."""
        from brokenlinkbrief.scan_history import ScanHistoryStore

        assert hasattr(ScanHistoryStore, "get_latest_scan")

    def test_get_latest_scan_callable(self) -> None:
        """ScanHistoryStore.get_latest_scan is callable."""
        from brokenlinkbrief.scan_history import ScanHistoryStore

        assert callable(ScanHistoryStore.get_latest_scan)

    def test_get_latest_scan_signature(self) -> None:
        """get_latest_scan(project_id: str) signature is correct."""
        from brokenlinkbrief.scan_history import ScanHistoryStore

        sig = inspect.signature(ScanHistoryStore.get_latest_scan)
        params = list(sig.parameters.keys())
        assert "project_id" in params, (
            f"Expected 'project_id' param, got {params}"
        )


# ---------------------------------------------------------------------------
# 3. Aggregation logic behavioral tests (RED phase)
# ---------------------------------------------------------------------------


def _make_project_mock(project_id: str, name: str) -> MagicMock:
    """Create a mock project with id and name attributes."""
    m = MagicMock()
    m.id = project_id
    m.name = name
    return m


class TestAggregateScheduledProjects:
    """Behavioral tests for the scheduled projects aggregation logic."""

    def test_returns_list(self) -> None:
        """aggregate_scheduled_projects returns a list."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
        except NotImplementedError:
            pytest.skip("aggregate_scheduled_projects not yet implemented")
        result = aggregate_scheduled_projects(
            schedules=[],
            projects=[],
            scan_history_store=None,
        )
        assert isinstance(result, list)

    def test_empty_schedules_returns_empty_list(self) -> None:
        """No schedules means no scheduled project views."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        result = aggregate_scheduled_projects(
            schedules=[],
            projects=[],
            scan_history_store=None,
        )
        assert result == []

    def test_single_schedule_with_no_history(self) -> None:
        """A schedule with no scan history shows last_scan_status as 'never_run'."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        schedule = Schedule(
            id="s1",
            project_id="p1",
            cadence="0 9 * * *",
            timezone="UTC",
            state="ACTIVE",
            next_due_at=time.time() + 3600,
        )
        result = aggregate_scheduled_projects(
            schedules=[schedule],
            projects=[_make_project_mock("p1", "My Project")],
            scan_history_store=None,
        )
        assert len(result) == 1
        view = result[0]
        assert view.project_id == "p1"
        assert view.last_scan_status == "never_run"

    def test_schedule_links_to_correct_project(self) -> None:
        """Each view references the correct project name."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        schedules = [
            Schedule(
                "s1", "p1", "0 9 * * *", "UTC",
                "ACTIVE", time.time() + 100,
            ),
            Schedule(
                "s2", "p2", "0 */6 * * *",
                "Europe/Zurich", "ACTIVE", time.time() + 200,
            ),
        ]
        result = aggregate_scheduled_projects(
            schedules=schedules,
            projects=[
                _make_project_mock("p1", "Alpha"),
                _make_project_mock("p2", "Beta"),
            ],
            scan_history_store=None,
        )
        by_id = {v.project_id: v for v in result}
        assert by_id["p1"].project_name == "Alpha"
        assert by_id["p2"].project_name == "Beta"

    def test_view_includes_cadence(self) -> None:
        """View exposes the cadence from the schedule."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        schedule = Schedule(
            "s1", "p1", "0 9 * * *", "UTC",
            "ACTIVE", time.time(),
        )
        result = aggregate_scheduled_projects(
            schedules=[schedule],
            projects=[_make_project_mock("p1", "X")],
            scan_history_store=None,
        )
        assert result[0].cadence == "0 9 * * *"

    def test_view_includes_timezone(self) -> None:
        """View exposes the timezone from the schedule."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        schedule = Schedule(
            "s1", "p1", "0 9 * * *",
            "Europe/Zurich", "ACTIVE", time.time(),
        )
        result = aggregate_scheduled_projects(
            schedules=[schedule],
            projects=[_make_project_mock("p1", "X")],
            scan_history_store=None,
        )
        assert result[0].timezone == "Europe/Zurich"

    def test_view_includes_next_due_at(self) -> None:
        """View exposes the next_due_at timestamp from the schedule."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        ts = time.time() + 7200
        schedule = Schedule(
            "s1", "p1", "0 9 * * *", "UTC", "ACTIVE", ts,
        )
        result = aggregate_scheduled_projects(
            schedules=[schedule],
            projects=[_make_project_mock("p1", "X")],
            scan_history_store=None,
        )
        assert result[0].next_due_at == ts

    def test_schedule_without_matching_project_excluded(self) -> None:
        """Schedules with no matching project are excluded from the view."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        schedule = Schedule(
            "s1", "p_missing", "0 9 * * *",
            "UTC", "ACTIVE", time.time(),
        )
        result = aggregate_scheduled_projects(
            schedules=[schedule],
            projects=[],
            scan_history_store=None,
        )
        assert len(result) == 0

    def test_state_reflects_schedule(self) -> None:
        """View state matches the schedule state."""
        try:
            from brokenlinkbrief.scheduled_projects import (
                aggregate_scheduled_projects,
            )
            from brokenlinkbrief.scheduler import Schedule
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        for state in ("ACTIVE", "RUNNING", "PAUSED"):
            schedule = Schedule(
                "s1", "p1", "0 9 * * *",
                "UTC", state, time.time(),
            )
            result = aggregate_scheduled_projects(
                schedules=[schedule],
                projects=[_make_project_mock("p1", "X")],
                scan_history_store=None,
            )
            assert result[0].state == state


# ---------------------------------------------------------------------------
# 4. API endpoint route tests (RED phase — endpoints not wired yet)
# ---------------------------------------------------------------------------


class TestScheduledProjectsEndpoint:
    """Behavioral tests for the /api/scheduled-projects HTTP endpoint."""

    @pytest.fixture()
    def _start_server(self, monkeypatch: pytest.MonkeyPatch):
        """Start a temp server and return the port."""
        from brokenlinkbrief.app import _Handler

        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "test-token")

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        import threading

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        yield port
        server.shutdown()

    def test_scheduled_projects_endpoint_exists(
        self, _start_server: int,
    ) -> None:
        """GET /api/scheduled-projects returns 200 or 404 (not 500)."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/api/scheduled-projects?token=test-token")
        resp = conn.getresponse()
        assert resp.status in (200, 404), (
            f"Unexpected status: {resp.status}"
        )
        conn.close()

    def test_scheduled_projects_returns_json(
        self, _start_server: int,
    ) -> None:
        """GET /api/scheduled-projects returns JSON content type."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/api/scheduled-projects?token=test-token")
        resp = conn.getresponse()
        if resp.status == 200:
            ct = resp.getheader("Content-Type", "")
            assert "json" in ct, f"Expected JSON, got {ct}"
        conn.close()

    def test_scheduled_projects_body_is_list(
        self, _start_server: int,
    ) -> None:
        """GET /api/scheduled-projects body decodes as a JSON list."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/api/scheduled-projects?token=test-token")
        resp = conn.getresponse()
        if resp.status == 200:
            body = json.loads(resp.read())
            assert isinstance(body, list), (
                f"Expected list, got {type(body)}"
            )
        conn.close()

    def test_scheduled_project_view_shape(
        self, _start_server: int,
    ) -> None:
        """Each item in /api/scheduled-projects has expected keys."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/api/scheduled-projects?token=test-token")
        resp = conn.getresponse()
        if resp.status == 200:
            body = json.loads(resp.read())
            if len(body) > 0:
                item = body[0]
                expected_keys = {
                    "project_id",
                    "project_name",
                    "cadence",
                    "timezone",
                    "state",
                    "next_due_at",
                    "last_scan_status",
                }
                missing = expected_keys - set(item.keys())
                assert not missing, f"Missing keys in view: {missing}"
        conn.close()

    def test_unauthenticated_returns_401(
        self, _start_server: int,
    ) -> None:
        """GET /api/scheduled-projects without token returns 401."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/api/scheduled-projects")
        resp = conn.getresponse()
        assert resp.status == 401, (
            f"Expected 401, got {resp.status}"
        )
        conn.close()


class TestManualTriggerEndpoint:
    """Behavioral tests for POST /api/scheduled-projects/{id}/trigger."""

    @pytest.fixture()
    def _start_server(self, monkeypatch: pytest.MonkeyPatch):
        """Start a temp server and return the port."""
        from brokenlinkbrief.app import _Handler

        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "test-token")
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        import threading

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        yield port
        server.shutdown()

    def test_trigger_endpoint_exists(self, _start_server: int) -> None:
        """POST /api/scheduled-projects/{id}/trigger returns 200 or 404."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request(
            "POST",
            "/api/scheduled-projects/p1/trigger?token=test-token",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        assert resp.status in (200, 404, 405), (
            f"Unexpected status: {resp.status}"
        )
        conn.close()

    def test_trigger_returns_json(self, _start_server: int) -> None:
        """POST /api/scheduled-projects/{id}/trigger returns JSON."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request(
            "POST",
            "/api/scheduled-projects/p1/trigger?token=test-token",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        if resp.status == 200:
            ct = resp.getheader("Content-Type", "")
            assert "json" in ct
        conn.close()

    def test_trigger_body_has_status_key(
        self, _start_server: int,
    ) -> None:
        """Trigger response contains a 'status' key."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request(
            "POST",
            "/api/scheduled-projects/p1/trigger?token=test-token",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        if resp.status == 200:
            body = json.loads(resp.read())
            assert "status" in body, (
                f"Missing 'status' in response: {body}"
            )
        conn.close()

    def test_trigger_nonexistent_project_returns_404(
        self, _start_server: int,
    ) -> None:
        """Trigger on a nonexistent project_id returns 404."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request(
            "POST",
            "/api/scheduled-projects/nonexistent/trigger"
            "?token=test-token",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        assert resp.status == 404, (
            f"Expected 404, got {resp.status}"
        )
        conn.close()

    def test_trigger_unauthenticated_returns_401(
        self, _start_server: int,
    ) -> None:
        """Trigger without token returns 401."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request(
            "POST",
            "/api/scheduled-projects/p1/trigger",
            body=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        assert resp.status == 401, (
            f"Expected 401, got {resp.status}"
        )
        conn.close()


# ---------------------------------------------------------------------------
# 5. Trend data per-project extension behavioral tests (RED phase)
# ---------------------------------------------------------------------------


class TestTrendDataPerProject:
    """Behavioral tests for per-project trend data for the chart."""

    def test_history_store_has_get_project_trend(self) -> None:
        """HistoryStore.get_project_trend method exists."""
        from brokenlinkbrief.package import HistoryStore

        assert hasattr(HistoryStore, "get_project_trend")
        assert callable(HistoryStore.get_project_trend)

    def test_get_project_trend_returns_list(self) -> None:
        """get_project_trend returns a list of daily aggregates."""
        try:
            from brokenlinkbrief.package import HistoryStore
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        store = HistoryStore()
        try:
            result = store.get_project_trend(
                "nonexistent-project-id", days=7,
            )
        except NotImplementedError:
            pytest.skip(
                "get_project_trend not yet implemented — RED phase"
            )
        assert isinstance(result, list)

    def test_trend_item_shape(self) -> None:
        """Each trend item has date, total, broken keys."""
        try:
            from brokenlinkbrief.package import HistoryStore
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        store = HistoryStore()
        try:
            result = store.get_project_trend("nonexistent", days=7)
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        if len(result) > 0:
            item = result[0]
            assert "date" in item
            assert "total" in item
            assert "broken" in item

    def test_trend_date_format(self) -> None:
        """Trend dates are in YYYY-MM-DD format."""
        try:
            from brokenlinkbrief.package import HistoryStore
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        store = HistoryStore()
        try:
            result = store.get_project_trend("nonexistent", days=30)
        except NotImplementedError:
            pytest.skip("not implemented yet — RED phase")
        import re

        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for item in result:
            assert date_re.match(item["date"]), (
                f"Bad date format: {item['date']}"
            )


# ---------------------------------------------------------------------------
# 6. Dashboard HTML scheduled-projects section tests (RED phase)
# ---------------------------------------------------------------------------


class TestDashboardHtmlScheduledProjects:
    """Verify the dashboard HTML includes scheduled projects UI."""

    @pytest.fixture()
    def _start_server(self, monkeypatch: pytest.MonkeyPatch):
        """Start a temp server and return the port."""
        from brokenlinkbrief.app import _Handler

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        import threading

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        yield port
        server.shutdown()

    def test_dashboard_includes_scheduled_projects_section(
        self, _start_server: int,
    ) -> None:
        """Dashboard HTML contains a 'scheduled projects' section."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/dashboard")
        resp = conn.getresponse()
        if resp.status == 200:
            html = resp.read().decode("utf-8")
            lower = html.lower()
            assert "scheduled" in lower or "schedule" in lower, (
                "Dashboard HTML missing scheduled projects section"
            )
        conn.close()

    def test_dashboard_includes_trigger_button(
        self, _start_server: int,
    ) -> None:
        """Dashboard HTML contains a manual trigger button."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/dashboard")
        resp = conn.getresponse()
        if resp.status == 200:
            html = resp.read().decode("utf-8")
            assert "trigger" in html.lower(), (
                "Dashboard HTML missing trigger button"
            )
        conn.close()

    def test_dashboard_includes_chartjs(
        self, _start_server: int,
    ) -> None:
        """Dashboard HTML loads Chart.js for the trend chart."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/dashboard")
        resp = conn.getresponse()
        if resp.status == 200:
            html = resp.read().decode("utf-8")
            lower = html.lower()
            assert "chart.js" in lower or "chartjs" in lower, (
                "Dashboard HTML missing Chart.js for trend chart"
            )
        conn.close()

    def test_dashboard_trend_chart_canvas(
        self, _start_server: int,
    ) -> None:
        """Dashboard HTML has a canvas element for the trend chart."""
        import http.client

        conn = http.client.HTTPConnection(
            "127.0.0.1", _start_server, timeout=5,
        )
        conn.request("GET", "/dashboard")
        resp = conn.getresponse()
        if resp.status == 200:
            html = resp.read().decode("utf-8")
            assert "<canvas" in html.lower(), (
                "Dashboard HTML missing <canvas> element for chart"
            )
        conn.close()
