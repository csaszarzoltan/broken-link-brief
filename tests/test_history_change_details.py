"""TDD acceptance coverage for actionable history change details."""

from __future__ import annotations

import http.client
import threading
from http.server import HTTPServer

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.package import HistoryStore, LinkResult


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_timeline_includes_newly_broken_and_fixed_link_details(tmp_path) -> None:
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
            LinkResult("https://target.test/a", 500, "Server Error"),
            LinkResult("https://target.test/b", 200, "OK"),
            LinkResult("https://target.test/c", 404, "Not Found"),
        ],
        "https://source.test",
    )

    latest = store.get_target_timeline("https://source.test", limit=10)[0]

    assert latest["newly_broken"] == [
        {"url": "https://target.test/a", "status": 500},
        {"url": "https://target.test/c", "status": 404},
    ]
    assert latest["fixed"] == [
        {"url": "https://target.test/b", "status": 200},
    ]


def test_timeline_change_details_are_deterministically_sorted(tmp_path) -> None:
    store = HistoryStore(tmp_path)
    store.record_scan(
        [
            LinkResult("https://target.test/z", 404, "Not Found"),
            LinkResult("https://target.test/a", 404, "Not Found"),
        ],
        "https://source.test",
    )

    latest = store.get_target_timeline("https://source.test", limit=10)[0]
    assert [item["url"] for item in latest["newly_broken"]] == [
        "https://target.test/a",
        "https://target.test/z",
    ]


def test_dashboard_history_renders_expandable_change_details() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Change details" in html
        assert "Newly broken links" in html
        assert "Fixed links" in html
        assert "renderChangeList" in html
    finally:
        server.shutdown()


def test_dashboard_history_exposes_export_action() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Export history JSON" in html
        assert "exportTargetHistory" in html
    finally:
        server.shutdown()
