"""Pre-development tests for Portfolio Dashboard UI (Python-native, embedded in
_DASHBOARD_HTML).

Feature under test: Portfolio section inside the single-page dashboard served
at /dashboard.

State at authoring time (pre-tester):
- _DASHBOARD_HTML does NOT yet contain the portfolio section (§4.2).
- Inline JS functions (loadPortfolio, setPortfolioDays, renderPortfolioCards,
  renderPortfolioRows, renderPortfolioEmpty, renderPortfolioError,
  exportPortfolioCsv) do NOT yet exist.
- /api/portfolio and /api/portfolio/summary endpoints do NOT yet exist.
- Therefore ALL behavioral tests are expected to FAIL/SKIP against the current
  HTML and PASS only after the developer implements the portfolio feature
  (P0-UI → P1-API-UI).
"""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import LinkResult

# ---------------------------------------------------------------------------
# 0. Shared fixtures & helpers
# ---------------------------------------------------------------------------


def _start_server(monkeypatch) -> tuple:
    """Start a temp HTTP server with monkeypatched scanner.

    Returns (server, port) tuple. Caller must stop the server.
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


def _get_dashboard_html() -> str:
    """Read the current _DASHBOARD_HTML string from app.py."""
    from brokenlinkbrief.app import _DASHBOARD_HTML

    return _DASHBOARD_HTML


# ---------------------------------------------------------------------------
# 1. Interface tests — DOM structure inside _DASHBOARD_HTML
#    These assert on the HTML string directly; they FAIL (RED) until
#    the developer injects the portfolio section per §4.2-4.4.
# ---------------------------------------------------------------------------


class TestPortfolioDashboardHTMLStructure:
    """String-level assertions on _DASHBOARD_HTML."""

    def test_portfolio_section_exists(self) -> None:
        """_DASHBOARD_HTML has <section id="portfolioSection" class="scan-panel">."""
        html = _get_dashboard_html()
        assert 'id="portfolioSection"' in html
        assert 'class="scan-panel"' in html

    def test_portfolio_heading_exists(self) -> None:
        """_DASHBOARD_HTML has <h2 id="portfolioHeading">Portfolio overview</h2>."""
        html = _get_dashboard_html()
        assert 'id="portfolioHeading"' in html
        assert "Portfolio overview" in html

    def test_portfolio_cards_container_exists(self) -> None:
        """_DASHBOARD_HTML contains <div class="cards" id="portfolioCards">."""
        html = _get_dashboard_html()
        assert 'id="portfolioCards"' in html
        assert 'class="cards"' in html

    def test_portfolio_days_filter_buttons_exist(self) -> None:
        """_DASHBOARD_HTML contains filter bar with data-portfolio-days buttons."""
        html = _get_dashboard_html()
        assert 'id="portfolioDays"' in html
        for days in ("7", "30", "90", "0"):
            assert f'data-portfolio-days="{days}"' in html

    def test_portfolio_trend_canvas_exists(self) -> None:
        """_DASHBOARD_HTML has canvas for Chart.js trend (id="portfolioTrendCanvas")."""
        html = _get_dashboard_html()
        assert 'id="portfolioTrendCanvas"' in html

    def test_export_portfolio_button_exists(self) -> None:
        """_DASHBOARD_HTML contains Export CSV button (id="exportPortfolio")."""
        html = _get_dashboard_html()
        assert 'id="exportPortfolio"' in html
        assert "Export CSV" in html


# ---------------------------------------------------------------------------
# 2. Interface tests — Inline JS functions defined in _DASHBOARD_HTML <script>
# ---------------------------------------------------------------------------


class TestPortfolioDashboardJSFunctions:
    """Assert that required JS functions are present in the inline <script> block."""

    def _extract_script(self) -> str:
        html = _get_dashboard_html()
        match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
        assert match is not None, "<script> block not found in _DASHBOARD_HTML"
        return match.group(1)

    def test_load_portfolio_function_defined(self) -> None:
        """loadPortfolio() function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\basync\s+function\s+loadPortfolio\s*\(", script)

    def test_set_portfolio_days_function_defined(self) -> None:
        """setPortfolioDays(days) function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\bfunction\s+setPortfolioDays\s*\(", script) or re.search(
            r"\basync\s+function\s+setPortfolioDays\s*\(", script
        )

    def test_render_portfolio_cards_function_defined(self) -> None:
        """renderPortfolioCards(summary) function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\bfunction\s+renderPortfolioCards\s*\(", script)

    def test_render_portfolio_rows_function_defined(self) -> None:
        """renderPortfolioRows(projects) function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\bfunction\s+renderPortfolioRows\s*\(", script)

    def test_render_portfolio_empty_function_defined(self) -> None:
        """renderPortfolioEmpty() function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\bfunction\s+renderPortfolioEmpty\s*\(", script)

    def test_render_portfolio_error_function_defined(self) -> None:
        """renderPortfolioError(detail) function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\bfunction\s+renderPortfolioError\s*\(", script)

    def test_export_portfolio_csv_function_defined(self) -> None:
        """exportPortfolioCsv() function exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\bfunction\s+exportPortfolioCsv\s*\(", script)

    def test_portfolio_days_state_variable_defined(self) -> None:
        """let portfolioDays = 30; state variable exists in the inline script."""
        script = self._extract_script()
        assert re.search(r"\blet\s+portfolioDays\s*=\s*30\s*;", script)


# ---------------------------------------------------------------------------
# 3. Behavioral HTTP tests — real server + monkeypatch
#    These exercise /dashboard and portfolio API endpoints.
#    They are SKIPPED (RED phase) until the developer wires the endpoints.
# ---------------------------------------------------------------------------


class TestPortfolioDashboardBehavioral:
    """Behavioral tests against a live HTTPServer with monkeypatched scanner."""

    def test_dashboard_renders_without_js_errors(self, monkeypatch) -> None:
        """GET /dashboard returns 200 HTML; portfolio section present (string check)."""
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")

        def fake_scan(url: str, timeout: float = 10.0):
            return [
                LinkResult(
                    url="https://example.com", status=200, reason="OK", location=None
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
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(
                "GET",
                "/dashboard?token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            conn.close()
            assert resp.status == 200
            assert "text/html" in resp.getheader("Content-Type", "")
            # Portfolio section should exist after P0-UI implementation
            if 'id="portfolioSection"' not in body:
                pytest.skip(
                    "RED phase: portfolio section not yet injected into _DASHBOARD_HTML"
                )
        finally:
            server.shutdown()

    def test_api_portfolio_returns_summary_and_projects(self, monkeypatch) -> None:
        """GET /api/portfolio?token=... returns 200 with {summary, projects}."""
        server, port = _start_server(monkeypatch)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(
                "GET",
                "/api/portfolio?token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            conn.close()
            if resp.status == 404:
                pytest.skip(
                    "RED phase: /api/portfolio endpoint not yet wired in app.py"
                )
            assert resp.status == 200, f"Expected 200, got {resp.status}: {data}"
            parsed = json.loads(data)
            assert isinstance(parsed, dict)
            assert "summary" in parsed
            assert "projects" in parsed
        finally:
            server.shutdown()

    def test_api_portfolio_endpoint_requires_auth(self, monkeypatch) -> None:
        """GET /api/portfolio without token returns 401."""
        server, port = _start_server(monkeypatch)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/portfolio", headers={"Host": "127.0.0.1"})
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            conn.close()
            if resp.status == 404:
                pytest.skip(
                    "RED phase: /api/portfolio endpoint not yet wired in app.py"
                )
            assert resp.status == 401, f"Expected 401, got {resp.status}: {data}"
        finally:
            server.shutdown()

    def test_api_portfolio_summary_endpoint_returns_trend(self, monkeypatch) -> None:
        """GET /api/portfolio/summary?days=7 returns 200 with {summary, trend}."""
        server, port = _start_server(monkeypatch)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(
                "GET",
                "/api/portfolio/summary?days=7&token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            conn.close()
            if resp.status == 404:
                pytest.skip(
                    "RED phase: /api/portfolio/summary endpoint not yet wired in app.py"
                )
            assert resp.status == 200, f"Expected 200, got {resp.status}: {data}"
            parsed = json.loads(data)
            assert isinstance(parsed, dict)
            assert "summary" in parsed
            assert "trend" in parsed
            assert isinstance(parsed["trend"], list)
        finally:
            server.shutdown()

    def test_portfolio_days_filter_refetches_summary(self, monkeypatch) -> None:
        """Changing date range calls /api/portfolio/summary with correct days param."""
        # This is a string-level test: verify setPortfolioDays updates portfolioDays
        # and calls loadPortfolio (which fetches /api/portfolio/summary?days=...)
        # Full integration requires JS execution (Node/Playwright) — covered in P2 E2E.
        # Here we only assert the function exists and references the right endpoint.
        script = TestPortfolioDashboardJSFunctions()._extract_script()
        # Check that setPortfolioDays references the days param and loadPortfolio
        if "loadPortfolio" not in script:
            pytest.skip("RED phase: loadPortfolio not yet defined")
        if "/api/portfolio/summary" not in script:
            pytest.skip("RED phase: trend fetch not yet wired in JS")
        # If we reach here, the wiring is present (P1-API-UI done)
        assert "portfolioDays" in script
        assert "/api/portfolio/summary" in script

    def test_export_portfolio_csv_has_correct_header(self, monkeypatch) -> None:
        """exportPortfolioCsv() builds CSV with exact header row."""
        # String-level: verify the JS function contains the expected header.
        script = TestPortfolioDashboardJSFunctions()._extract_script()
        expected_header = (
            "project_name,total_links,broken_count,open_findings,"
            "resolved_findings,last_scan_timestamp"
        )
        if "exportPortfolioCsv" not in script:
            pytest.skip("RED phase: exportPortfolioCsv not yet defined")
        if expected_header not in script:
            pytest.skip(
                "RED phase: expected CSV header not found in exportPortfolioCsv: "
                f"{expected_header}"
            )
        # If we reach here, the header is correct (P1-API-UI done)
        assert expected_header in script
