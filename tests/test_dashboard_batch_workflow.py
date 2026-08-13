"""TDD acceptance coverage for the browser batch-scan workflow."""

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


def test_dashboard_exposes_single_and_batch_scan_modes() -> None:
    html = _dashboard_html()
    assert 'data-scan-mode="single"' in html
    assert 'data-scan-mode="batch"' in html
    assert 'id="batchScanPanel"' in html
    assert "Single page" in html
    assert "Multiple pages" in html


def test_batch_form_has_bulk_url_and_concurrency_inputs() -> None:
    html = _dashboard_html()
    assert 'id="batchUrls"' in html
    assert "<textarea" in html
    assert 'id="batchConcurrency"' in html
    assert 'min="1"' in html
    assert 'max="20"' in html
    assert "Run batch scan" in html


def test_batch_workflow_normalizes_and_detects_duplicate_urls() -> None:
    html = _dashboard_html()
    assert "parseBatchUrls" in html
    assert "duplicate URLs" in html
    assert "up to 50 unique public URLs" in html


def test_batch_workflow_uses_existing_result_review_tools() -> None:
    html = _dashboard_html()
    assert "runBatchScan" in html
    assert "flattenBatchResults" in html
    assert "showScanResults" in html
    assert "/scan-batch" in html


def test_batch_status_is_announced_accessibly() -> None:
    html = _dashboard_html()
    assert 'id="batchStatus"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
