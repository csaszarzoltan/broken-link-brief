"""TDD coverage for one-action project scanning and project health summaries."""

from __future__ import annotations

import http.client
import json
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import LinkResult
from brokenlinkbrief.projects import ProjectStore


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_project_summary_aggregates_latest_target_scans(tmp_path) -> None:
    project_store = ProjectStore(tmp_path / "projects.db")
    project = project_store.create(
        "Portfolio", ["https://one.test", "https://two.test"]
    )

    from brokenlinkbrief.package import HistoryStore

    history = HistoryStore(tmp_path / "history")
    history.record_scan(
        [LinkResult("https://one.test/a", 404, "Not Found")],
        "https://one.test/",
    )
    history.record_scan(
        [LinkResult("https://two.test/a", 200, "OK")],
        "https://two.test/",
    )

    summary = project_store.summarize(project, history)
    assert summary["scanned_targets"] == 2
    assert summary["unscanned_targets"] == 0
    assert summary["total_links"] == 2
    assert summary["broken_count"] == 1
    assert summary["last_scan_timestamp"] is not None


def test_project_summary_reports_unscanned_targets(tmp_path) -> None:
    project_store = ProjectStore(tmp_path / "projects.db")
    project = project_store.create(
        "Portfolio", ["https://one.test", "https://two.test"]
    )
    from brokenlinkbrief.package import HistoryStore

    summary = project_store.summarize(project, HistoryStore(tmp_path / "history"))
    assert summary["scanned_targets"] == 0
    assert summary["unscanned_targets"] == 2
    assert summary["last_scan_timestamp"] is None


def test_projects_api_includes_latest_health_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.setenv("BROKENLINKBRIEF_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    project = ProjectStore().create("Docs", ["https://example.com"])

    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/projects")
        response = conn.getresponse()
        projects = json.loads(response.read())
        assert response.status == 200
        assert projects[0]["id"] == project.id
        assert projects[0]["scan_summary"]["unscanned_targets"] == 1
    finally:
        server.shutdown()


def test_dashboard_exposes_one_action_project_scan() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Run project scan" in html
        assert "runProjectScan" in html
        assert "Never scanned" in html
        assert "need attention" in html
    finally:
        server.shutdown()
