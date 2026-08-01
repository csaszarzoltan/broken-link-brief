"""TDD coverage for durable saved projects and dashboard project workflow."""
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


def test_project_store_creates_normalized_project(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    created = store.create(" Main website ", [
        "https://example.com/", "https://example.org", "https://example.com/"
    ])
    assert created.name == "Main website"
    assert created.targets == ("https://example.com/", "https://example.org/")
    assert created.archived is False
    assert store.get(created.id) == created


def test_project_store_rejects_empty_name_and_targets(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    with pytest.raises(ValueError, match="name"):
        store.create(" ", ["https://example.com"])
    with pytest.raises(ValueError, match="target"):
        store.create("Site", [])


def test_project_store_archives_without_deleting(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    created = store.create("Site", ["https://example.com"])
    archived = store.archive(created.id)
    assert archived.archived is True
    assert store.list_active() == []
    assert store.get(created.id).archived is True


def test_projects_api_create_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps({"name": "Docs", "targets": ["https://example.com"]})
        conn.request("POST", "/api/projects", body=body,
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        created = json.loads(response.read())
        assert response.status == 201
        assert created["name"] == "Docs"

        conn.request("GET", "/api/projects")
        response = conn.getresponse()
        projects = json.loads(response.read())
        assert response.status == 200
        assert projects[0]["id"] == created["id"]
    finally:
        server.shutdown()


def test_projects_api_validates_targets(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps({"name": "Unsafe", "targets": ["http://127.0.0.1"]})
        conn.request("POST", "/api/projects", body=body,
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 400
        assert payload["code"] == "unsafe_target"
    finally:
        server.shutdown()


def test_dashboard_exposes_saved_project_workflow() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert 'id="projectForm"' in html
        assert 'id="projectList"' in html
        assert "Save project" in html
        assert "Load targets" in html
        assert "loadProjects" in html
    finally:
        server.shutdown()

def test_projects_api_archives_project(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    created = ProjectStore().create("Docs", ["https://example.com"])
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("DELETE", f"/api/projects/{created.id}")
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["archived"] is True
        assert ProjectStore().list_active() == []
    finally:
        server.shutdown()


def test_dashboard_exposes_archive_project_action() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Archive" in html
        assert "archiveProject" in html
    finally:
        server.shutdown()
