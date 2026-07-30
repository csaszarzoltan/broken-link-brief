"""Pre-development acceptance tests for BrokenLinkBrief Dashboard.

Feature under test: Dashboard UI and Data API for aggregated scan stats.

State at authoring time (pre-tester):
- HistoryStore.get_dashboard_summary() DOES NOT yet exist in package.py.
- HistoryStore.get_trend_data() DOES NOT yet exist in package.py.
- HistoryStore.get_severity_breakdown() DOES NOT yet exist in package.py.
- HistoryStore.get_domain_breakdown() DOES NOT yet exist in package.py.
- /api/dashboard/* endpoints DO NOT yet exist in app.py.
- /dashboard HTML endpoint DOES NOT yet exist in app.py.
- Therefore ALL behavioral tests are expected to FAIL against the stubs
  and PASS only after the developer implements the dashboard feature.
"""
from __future__ import annotations

import http.client
import json
import socket
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import LinkResult

# ---------------------------------------------------------------------------
# 1. Dashboard API Interface Tests (import/signature checks)
# ---------------------------------------------------------------------------


def test_interface_dashboard_summary_importable() -> None:
    """HistoryStore.get_dashboard_summary() must be callable."""
    from brokenlinkbrief.package import HistoryStore

    assert hasattr(HistoryStore, "get_dashboard_summary")
    assert callable(HistoryStore.get_dashboard_summary)


def test_interface_dashboard_trend_data_importable() -> None:
    """HistoryStore.get_trend_data() must be callable."""
    from brokenlinkbrief.package import HistoryStore

    assert hasattr(HistoryStore, "get_trend_data")
    assert callable(HistoryStore.get_trend_data)


def test_interface_dashboard_severity_breakdown_importable() -> None:
    """HistoryStore.get_severity_breakdown() must be callable."""
    from brokenlinkbrief.package import HistoryStore

    assert hasattr(HistoryStore, "get_severity_breakdown")
    assert callable(HistoryStore.get_severity_breakdown)


def test_interface_dashboard_domain_breakdown_importable() -> None:
    """HistoryStore.get_domain_breakdown() must be callable."""
    from brokenlinkbrief.package import HistoryStore

    assert hasattr(HistoryStore, "get_domain_breakdown")
    assert callable(HistoryStore.get_domain_breakdown)


# ---------------------------------------------------------------------------
# 2. Dashboard Data API Behavioral Tests
# ---------------------------------------------------------------------------


def _start_server(monkeypatch) -> tuple:
    """Helper: start a temp server with monkeypatched scanner and dashboard mocks.

    Returns (server, port) tuple.
    """
    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")

    def fake_scan(url: str, timeout: float = 10.0):
        return [
            LinkResult(
                url="https://example.com", status=200, reason="OK", location=None
            ),
            LinkResult(
                url="https://broken.com", status=404, reason="Not Found", location=None
            ),
        ]

    monkeypatch.setattr("brokenlinkbrief.app.scan_page", fake_scan)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_api_dashboard_summary_returns_aggregate_stats() -> None:
    """GET /api/dashboard/summary returns JSON with total_scans, total_broken,
    total_links, unique_urls, last_scan_timestamp."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/api/dashboard/summary?token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200, f"Expected 200, got {resp.status}: {data}"

        parsed = json.loads(data)
        assert isinstance(parsed, dict)
        assert "total_scans" in parsed
        assert "total_broken" in parsed
        assert "total_links" in parsed
        assert "unique_urls" in parsed
        assert "last_scan_timestamp" in parsed
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_api_dashboard_trends_returns_time_series() -> None:
    """GET /api/dashboard/trends?days=7 returns array of {date, total, broken}."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/api/dashboard/trends?days=7&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200, f"Expected 200, got {resp.status}: {data}"

        parsed = json.loads(data)
        assert isinstance(parsed, list)
        if len(parsed) > 0:
            entry = parsed[0]
            assert "date" in entry
            assert "total" in entry
            assert "broken" in entry
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_api_dashboard_severity_returns_breakdown() -> None:
    """GET /api/dashboard/severity?days=7 returns {critical, warning, info}."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/api/dashboard/severity?days=7&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200, f"Expected 200, got {resp.status}: {data}"

        parsed = json.loads(data)
        assert isinstance(parsed, dict)
        assert "critical" in parsed
        assert "warning" in parsed
        assert "info" in parsed
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_api_dashboard_domains_returns_domain_list() -> None:
    """GET /api/dashboard/domains?days=7 returns array of {domain, count}."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "GET",
            "/api/dashboard/domains?days=7&token=secret",
            headers={"Host": "127.0.0.1"},
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200, f"Expected 200, got {resp.status}: {data}"

        parsed = json.loads(data)
        assert isinstance(parsed, list)
        if len(parsed) > 0:
            entry = parsed[0]
            assert "domain" in entry
            assert "count" in entry
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_api_dashboard_all_endpoints_accept_auth() -> None:
    """All dashboard API endpoints respect token auth when configured."""
    endpoints = [
        "/api/dashboard/summary",
        "/api/dashboard/trends?days=7",
        "/api/dashboard/severity?days=7",
        "/api/dashboard/domains?days=7",
    ]

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        for endpoint in endpoints:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            sep = "&" if "?" in endpoint else "?"
            conn.request(
                "GET",
                f"{endpoint}{sep}token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 200, (
                f"Endpoint {endpoint} with valid token returned {resp.status}"
            )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_api_dashboard_endpoints_missing_auth_return_401() -> None:
    """Missing/invalid token returns 401 for all dashboard API endpoints."""
    endpoints = [
        "/api/dashboard/summary",
        "/api/dashboard/trends?days=7",
        "/api/dashboard/severity?days=7",
        "/api/dashboard/domains?days=7",
    ]

    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        for endpoint in endpoints:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            # No token provided
            conn.request("GET", endpoint, headers={"Host": "127.0.0.1"})
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 401, (
                f"Endpoint {endpoint} without token returned "
                f"{resp.status}, expected 401"
            )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_api_dashboard_all_endpoints_handle_empty_history() -> None:
    """All dashboard endpoints return valid JSON when no history exists."""
    endpoints = [
        "/api/dashboard/summary",
        "/api/dashboard/trends?days=7",
        "/api/dashboard/severity?days=7",
        "/api/dashboard/domains?days=7",
    ]

    monkeypatch = pytest.MonkeyPatch()
    # Override history directory to an empty temp dir so no history exists
    import tempfile

    tmpdir = tempfile.mkdtemp()
    monkeypatch.setattr("brokenlinkbrief.package._HISTORY_DIR", tmpdir)

    server, port = _start_server(monkeypatch)
    try:
        for endpoint in endpoints:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            sep = "&" if "?" in endpoint else "?"
            conn.request(
                "GET",
                f"{endpoint}{sep}token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            conn.close()
            # With no history, valid JSON (empty/zero values) is expected
            # The endpoint itself should exist and return 200
            assert resp.status == 200, (
                f"Endpoint {endpoint} with empty history returned {resp.status}: {data}"
            )
            parsed = json.loads(data)
            assert parsed is not None
    finally:
        server.shutdown()
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# 3. Dashboard UI Tests
# ---------------------------------------------------------------------------


def test_dashboard_html_endpoint_exists() -> None:
    """GET /dashboard returns 200 with Content-Type: text/html."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/dashboard", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200, f"Expected 200, got {resp.status}: {data[:200]}"
        content_type = resp.getheader("Content-Type", "")
        assert "text/html" in content_type, (
            f"Expected text/html content type, got: {content_type}"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_dashboard_html_contains_chartjs_cdn() -> None:
    """HTML includes <script> pointing to Chart.js CDN."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/dashboard", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        # Check for Chart.js CDN script reference
        chartjs_ref = (
            "chart.js" in html.lower()
            or "chartjs" in html.lower()
            or "cdn" in html.lower()
        )
        assert chartjs_ref, (
            "Dashboard HTML must include a Chart.js CDN script reference"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_dashboard_html_has_dark_theme_css() -> None:
    """HTML includes dark-theme style definitions."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/dashboard", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        # Check for dark theme indicators
        has_dark_bg = (
            "background" in html
            and (
                "#1a" in html
                or "#222" in html
                or "#2d" in html
            )
        )
        has_dark_css = "dark" in html.lower() and "color" in html
        assert has_dark_bg or has_dark_css, (
            "Dashboard HTML must include dark-theme color scheme definitions"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_dashboard_html_has_chart_canvases() -> None:
    """HTML contains <canvas> elements for trend, severity, domain charts."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/dashboard", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        canvas_count = html.count("<canvas")
        assert canvas_count >= 3, (
            f"Expected at least 3 <canvas> elements (trend, severity, domain), "
            f"found {canvas_count}"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_dashboard_html_has_date_range_controls() -> None:
    """HTML includes 7/30/90/all day filter buttons."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/dashboard", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        # Check for day-range filter controls
        has_7 = "7" in html
        has_30 = "30" in html
        has_90 = "90" in html
        assert has_7 and has_30 and has_90, (
            "Dashboard HTML must include 7, 30, and 90 day filter controls"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_dashboard_html_has_summary_cards() -> None:
    """HTML includes stat card elements for summary statistics."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/dashboard", headers={"Host": "127.0.0.1"})
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 200

        # Check for summary card indicators
        has_card = "card" in html.lower()
        has_stat = "stat" in html.lower()
        assert has_card or has_stat, (
            "Dashboard HTML must include stat card elements for summary statistics"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()
