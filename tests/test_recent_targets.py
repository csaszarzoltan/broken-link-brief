"""TDD acceptance coverage for repeat-user recent target workflows."""

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


def test_history_store_returns_recent_unique_targets(tmp_path) -> None:
    store = HistoryStore(tmp_path)
    store.record_scan([LinkResult("https://one.test/a", 200, "OK")], "https://one.test")
    store.record_scan(
        [LinkResult("https://two.test/a", 404, "Not Found")], "https://two.test"
    )
    store.record_scan(
        [LinkResult("https://one.test/b", 404, "Not Found")], "https://one.test"
    )

    recent = store.get_recent_targets(limit=10)

    assert [item["url"] for item in recent] == ["https://one.test", "https://two.test"]
    assert recent[0]["broken_count"] == 1
    assert recent[0]["total_links"] == 1
    assert recent[0]["last_scan_timestamp"] >= recent[1]["last_scan_timestamp"]


def test_recent_targets_endpoint_returns_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class Store:
        def get_recent_targets(self, limit=10):
            assert limit == 5
            return [
                {
                    "url": "https://example.com",
                    "last_scan_timestamp": "2026-08-01T10:00:00+00:00",
                    "total_links": 2,
                    "broken_count": 1,
                }
            ]

    monkeypatch.setattr("brokenlinkbrief.app.HistoryStore", Store)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/dashboard/recent-targets?limit=5")
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload[0]["url"] == "https://example.com"
    finally:
        server.shutdown()


def test_recent_targets_limit_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class Store:
        def get_recent_targets(self, limit=10):
            captured["limit"] = limit
            return []

    monkeypatch.setattr("brokenlinkbrief.app.HistoryStore", Store)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/dashboard/recent-targets?limit=500")
        response = conn.getresponse()
        response.read()
        assert response.status == 200
        assert captured["limit"] == 50
    finally:
        server.shutdown()


def test_dashboard_has_recent_targets_and_rescan_action() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert 'id="recentTargets"' in html
        assert "Recent pages" in html
        assert "Scan again" in html
        assert "loadRecentTargets" in html
    finally:
        server.shutdown()
