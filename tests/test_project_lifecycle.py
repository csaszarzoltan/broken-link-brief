"""TDD coverage for editing, restoring, and viewing archived projects."""

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


def test_project_store_updates_name_and_targets(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    project = store.create("Old", ["https://example.com"])
    updated = store.update(
        project.id,
        " Main site ",
        [
            "https://example.org/docs",
            "https://example.org/docs",
            "https://example.net",
        ],
    )
    assert updated.id == project.id
    assert updated.name == "Main site"
    assert updated.targets == (
        "https://example.org/docs",
        "https://example.net/",
    )
    assert updated.updated_at >= project.updated_at


def test_project_store_restores_archived_project(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    project = store.create("Site", ["https://example.com"])
    store.archive(project.id)
    restored = store.restore(project.id)
    assert restored.archived is False
    assert [item.id for item in store.list_active()] == [project.id]


def test_project_store_lists_archived_separately(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    active = store.create("Active", ["https://example.com"])
    archived = store.create("Archived", ["https://example.org"])
    store.archive(archived.id)
    assert [item.id for item in store.list_active()] == [active.id]
    assert [item.id for item in store.list_archived()] == [archived.id]


def test_projects_api_updates_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    project = ProjectStore().create("Old", ["https://example.com"])
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps({"name": "Updated", "targets": ["https://example.org"]})
        conn.request(
            "PUT",
            f"/api/projects/{project.id}",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["name"] == "Updated"
        assert payload["targets"] == ["https://example.org/"]
    finally:
        server.shutdown()


def test_projects_api_lists_and_restores_archived(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    store = ProjectStore()
    project = store.create("Archived", ["https://example.com"])
    store.archive(project.id)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/api/projects?archived=1")
        response = conn.getresponse()
        projects = json.loads(response.read())
        assert response.status == 200
        assert projects[0]["archived"] is True

        conn.request("POST", f"/api/projects/{project.id}/restore", body=b"")
        response = conn.getresponse()
        restored = json.loads(response.read())
        assert response.status == 200
        assert restored["archived"] is False
    finally:
        server.shutdown()


def test_dashboard_exposes_edit_and_archived_project_workflows() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Edit" in html
        assert "Show archived" in html
        assert "Restore" in html
        assert "editProject" in html
        assert "restoreProject" in html
        assert "cancelProjectEdit" in html
    finally:
        server.shutdown()
