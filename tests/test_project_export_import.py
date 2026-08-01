"""TDD coverage for portable project configuration export and import."""
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


def test_project_store_exports_versioned_configuration(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    project = store.create("Docs", ["https://example.com/docs"])
    payload = store.export_configuration(project.id)
    assert payload == {
        "schema_version": 1,
        "name": "Docs",
        "targets": ["https://example.com/docs"],
    }


def test_project_store_imports_with_new_identity(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    imported = store.import_configuration({
        "schema_version": 1,
        "name": "Imported",
        "targets": ["https://example.com", "https://example.com"],
    })
    assert imported.name == "Imported"
    assert imported.targets == ("https://example.com/",)
    assert imported.id


def test_project_store_rejects_unsupported_import_schema(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects.db")
    with pytest.raises(ValueError, match="schema"):
        store.import_configuration({
            "schema_version": 99,
            "name": "Future",
            "targets": ["https://example.com"],
        })


def test_project_export_api_returns_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    project = ProjectStore().create("Docs", ["https://example.com"])
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", f"/api/projects/{project.id}/export")
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["schema_version"] == 1
        assert payload["name"] == "Docs"
    finally:
        server.shutdown()


def test_project_import_api_validates_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(tmp_path / "projects.db"))
    monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        body = json.dumps({
            "schema_version": 1,
            "name": "Unsafe",
            "targets": ["http://127.0.0.1"],
        })
        conn.request("POST", "/api/projects/import", body=body,
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        payload = json.loads(response.read())
        assert response.status == 400
        assert payload["code"] == "unsafe_target"
    finally:
        server.shutdown()


def test_dashboard_exposes_project_export_import_workflow() -> None:
    server = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request("GET", "/dashboard")
        response = conn.getresponse()
        html = response.read().decode()
        assert response.status == 200
        assert "Export project" in html
        assert "Import project" in html
        assert 'id="projectImportFile"' in html
        assert "exportProject" in html
        assert "importProject" in html
    finally:
        server.shutdown()
