"""TDD acceptance coverage for target history and change-focused review."""

from __future__ import annotations

import http.client
import json
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import HistoryStore, LinkResult


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_target_timeline_summarizes_changes(tmp_path) -> None:
    store = HistoryStore(tmp_path)
    store.record_scan(
        [
            LinkResult("https://target.test/a", 200, "OK"),
            LinkResult("https://target.test/b", 404, "Not Found"),
        ],
        "https://source.test",
    )
    store.record_scan(
        [
            LinkResult("https://target.test/a", 404, "Not Found"),
            LinkResult("https://target.test/b", 200, "OK"),
            LinkResult("https://target.test/c", 500, "Server Error"),
        ],
        "https://source.test",
    )

    timeline = store.get_target_timeline("https://source.test", limit=10)

    assert len(timeline) == 2
    assert timeline[0]["total_links"] == 3
    assert timeline[0]["broken_count"] == 2
    assert timeline[0]["newly_broken_count"] == 2
    assert timeline[0]["fixed_count"] == 1
    assert timeline[1]["newly_broken_count"] == 1
    assert timeline[1]["fixed_count"] == 0


def test_target_history_endpoint_requires_url() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/dashboard/target-history")
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 400
        assert payload["code"] == "missing_url"
    finally:
        server.shutdown()


def test_target_history_endpoint_returns_timeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class Store:
        def get_target_timeline(self, url, limit=10):
            captured.update(url=url, limit=limit)
            return [
                {
                    "timestamp": "2026-08-01T10:00:00+00:00",
                    "total_links": 4,
                    "broken_count": 1,
                    "newly_broken_count": 1,
                    "fixed_count": 0,
                }
            ]

    monkeypatch.setattr("brokenlinkbrief.app.HistoryStore", Store)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request(
            "GET", "/api/dashboard/target-history?url=https%3A%2F%2Fexample.com&limit=4"
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload[0]["broken_count"] == 1
        assert captured == {"url": "https://example.com", "limit": 4}
    finally:
        server.shutdown()


def test_dashboard_exposes_history_dialog_and_action() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert 'id="historyDialog"' in html
        assert 'id="historyContent"' in html
        assert "View history" in html
        assert "loadTargetHistory" in html
        assert "Newly broken" in html
        assert "Fixed" in html
    finally:
        server.shutdown()
