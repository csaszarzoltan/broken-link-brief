"""TDD acceptance coverage for dashboard result review tools."""
from __future__ import annotations

import http.client
import threading
from http.server import HTTPServer

from brokenlinkbrief.app import _Handler


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _dashboard_html() -> str:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        return html
    finally:
        server.shutdown()


def test_dashboard_has_result_filter_controls() -> None:
    html = _dashboard_html()
    assert 'id="resultTools"' in html
    assert 'data-result-filter="all"' in html
    assert 'data-result-filter="attention"' in html
    assert 'data-result-filter="healthy"' in html
    assert "All results" in html
    assert "Needs attention" in html
    assert "Healthy" in html


def test_dashboard_has_result_search() -> None:
    html = _dashboard_html()
    assert 'id="resultSearch"' in html
    assert 'type="search"' in html
    assert "Search results" in html
    assert "applyResultView" in html


def test_dashboard_has_csv_export_for_visible_results() -> None:
    html = _dashboard_html()
    assert 'id="exportResults"' in html
    assert "Export visible CSV" in html
    assert "exportVisibleResults" in html
    assert "escapeCsvCell" in html


def test_result_tools_have_accessible_live_count() -> None:
    html = _dashboard_html()
    assert 'id="visibleResultCount"' in html
    assert 'aria-live="polite"' in html
    assert "results shown" in html
