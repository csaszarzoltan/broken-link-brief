"""TDD coverage for duplicating saved projects."""
from __future__ import annotations

import http.client
import json
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.projects import ProjectStore


def _server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_project_store_duplicates_project_with_new_identity(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    source = store.create("Main site", [
        "https://example.com/", "https://example.com/docs"
    ])

    duplicate = store.duplicate(source.id)

    assert duplicate.id != source.id
    assert duplicate.name == "Main site copy"
    assert duplicate.targets == source.targets
    assert duplicate.archived is False


def test_project_store_uses_available_copy_name(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    source = store.create("Main site", ["https://example.com"])
    first = store.duplicate(source.id)
    second = store.duplicate(source.id)

    assert first.name == "Main site copy"
    assert second.name == "Main site copy 2"


def test_project_duplicate_api_returns_new_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    source = ProjectStore().create("Docs", ["https://example.com"])
    server = _server()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request("POST", f"/api/projects/{source.id}/duplicate", body=b"")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 201
        assert payload["id"] != source.id
        assert payload["name"] == "Docs copy"
        assert payload["targets"] == ["https://example.com/"]
    finally:
        server.shutdown()


def test_project_duplicate_api_requires_existing_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    server = _server()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request("POST", "/api/projects/missing/duplicate", body=b"")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 404
        assert payload["code"] == "project_not_found"
    finally:
        server.shutdown()


def test_dashboard_exposes_duplicate_project_action() -> None:
    server = _server()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        connection.request("GET", "/dashboard")
        response = connection.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Duplicate" in html
        assert "duplicateProject" in html
        assert "Duplicated" in html
    finally:
        server.shutdown()
