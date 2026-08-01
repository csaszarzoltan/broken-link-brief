"""Acceptance tests for the user-centered 1.1 dashboard and API consistency."""
from __future__ import annotations

import http.client
import json
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief import __version__
from brokenlinkbrief.app import _Handler, run_health_checks


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_health_reports_package_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brokenlinkbrief.app._check_external_http", lambda: type("C", (), {"name": "external_http", "status": "healthy"})())
    monkeypatch.setattr("brokenlinkbrief.app._check_history_store", lambda: type("C", (), {"name": "history_store", "status": "healthy"})())
    monkeypatch.setattr("brokenlinkbrief.app._check_dns_resolution", lambda: type("C", (), {"name": "dns_resolution", "status": "healthy"})())
    assert run_health_checks().version == __version__


def test_dashboard_exposes_primary_scan_workflow() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert 'id="scanForm"' in html
        assert 'aria-live="polite"' in html
        assert 'id="scanResults"' in html
        assert "Run scan" in html
        assert "Skip to results" in html
    finally:
        server.shutdown()


def test_single_scan_rejects_unsafe_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/scan?url=http%3A%2F%2F127.0.0.1")
        response = conn.getresponse()
        data = json.loads(response.read())
        assert response.status == 400
        assert data["code"] == "unsafe_target"
    finally:
        server.shutdown()


def test_dashboard_summary_honors_days(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Store:
        def get_dashboard_summary(self, since=None, until=None):
            captured["since"] = since
            return {"total_scans": 0, "total_broken": 0, "total_links": 0,
                    "unique_urls": 0, "last_scan_timestamp": None}

    monkeypatch.setattr("brokenlinkbrief.app.HistoryStore", Store)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/dashboard/summary?days=30")
        response = conn.getresponse()
        response.read()
        assert response.status == 200
        assert isinstance(captured.get("since"), str)
    finally:
        server.shutdown()
