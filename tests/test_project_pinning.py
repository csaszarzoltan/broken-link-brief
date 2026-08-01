"""TDD coverage for pinning frequently used projects."""
from __future__ import annotations

import http.client
import json
import sqlite3
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.projects import ProjectStore


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_project_store_pins_and_orders_active_projects(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    first = store.create("First", ["https://first.example"])
    second = store.create("Second", ["https://second.example"])

    pinned = store.set_pinned(first.id, True)

    assert pinned.pinned is True
    assert [item.id for item in store.list_active()] == [first.id, second.id]
    assert store.set_pinned(first.id, False).pinned is False


def test_project_store_migrates_existing_database(tmp_path) -> None:
    path = tmp_path / "projects.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE project_targets (project_id TEXT NOT NULL, "
            "position INTEGER NOT NULL, url TEXT NOT NULL, "
            "PRIMARY KEY(project_id, url))"
        )
    store = ProjectStore(path)
    project = store.create("Migrated", ["https://example.com"])
    assert project.pinned is False
    assert store.set_pinned(project.id, True).pinned is True


def test_project_duplicate_does_not_copy_pin(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    source = store.create("Pinned", ["https://example.com"])
    store.set_pinned(source.id, True)
    duplicate = store.duplicate(source.id)
    assert duplicate.pinned is False


def test_project_pin_api_updates_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    project = ProjectStore().create("Docs", ["https://example.com"])
    server = _server()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request(
            "POST",
            f"/api/projects/{project.id}/pin",
            body=json.dumps({"pinned": True}),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["pinned"] is True
    finally:
        server.shutdown()


def test_dashboard_exposes_pin_project_action() -> None:
    server = _server()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request("GET", "/dashboard")
        response = connection.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Pin" in html
        assert "Unpin" in html
        assert "toggleProjectPin" in html
        assert "Pinned projects appear first" in html
    finally:
        server.shutdown()
