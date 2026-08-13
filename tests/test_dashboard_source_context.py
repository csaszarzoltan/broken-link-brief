"""TDD acceptance coverage for source-aware batch result review."""

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
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request("GET", "/dashboard")
        response = connection.getresponse()
        html = response.read().decode()
        assert response.status == 200
        return html
    finally:
        server.shutdown()


def test_batch_results_preserve_source_page_context() -> None:
    html = _dashboard_html()
    assert "source_url" in html
    assert "flattenBatchResults" in html
    assert "Source page" in html


def test_result_tools_include_source_page_filter() -> None:
    html = _dashboard_html()
    assert 'id="sourceFilter"' in html
    assert "All source pages" in html
    assert "populateSourceFilter" in html


def test_result_search_includes_source_page() -> None:
    html = _dashboard_html()
    assert "item.source_url" in html
    assert "Search results" in html


def test_visible_csv_contains_source_page_column() -> None:
    html = _dashboard_html()
    assert "source_url', 'url', 'status', 'reason', 'location" in html
    assert "item.source_url, item.url" in html


def test_single_scan_assigns_current_target_as_source_context() -> None:
    html = _dashboard_html()
    assert "attachSourceContext" in html
    assert "input.value.trim()" in html
