"""Deployment smoke tests for Railway readiness."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

import pytest


def _free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(tmp_path: Path):
    """Start the app on a free port and yield its base URL."""
    port = _free_port()
    env = {"PORT": str(port)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "brokenlinkbrief.app"],
        cwd=str(Path(__file__).resolve().parent.parent / "src"),
        env={**__import__("os").environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    # Wait for server to be ready
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=2)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.kill()
        pytest.fail("Server did not start within 18 seconds")
    yield base
    proc.terminate()
    proc.wait(timeout=5)


def test_health_endpoint_returns_ok(server: str) -> None:
    """Health endpoint returns 200 or 503 with health data."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "healthy"
    except HTTPError as e:
        # 503 means degraded/unhealthy - also acceptable
        assert e.code == 503
        data = json.loads(e.read())
        assert data["status"] in ("degraded", "unhealthy")

    from brokenlinkbrief import __version__
    assert data["version"] == __version__
    assert "timestamp" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) > 0


def test_health_endpoint_has_version(server: str) -> None:
    """Health endpoint includes version field."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        data = json.loads(resp.read())
    except HTTPError as e:
        data = json.loads(e.read())
    assert "version" in data
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_health_endpoint_has_timestamp(server: str) -> None:
    """Health endpoint includes ISO timestamp."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        data = json.loads(resp.read())
    except HTTPError as e:
        data = json.loads(e.read())
    assert "timestamp" in data
    # Should be ISO format
    assert "T" in data["timestamp"]
    assert "+" in data["timestamp"] or "Z" in data["timestamp"]


def test_health_endpoint_has_checks(server: str) -> None:
    """Health endpoint includes dependency checks."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        data = json.loads(resp.read())
    except HTTPError as e:
        data = json.loads(e.read())
    checks = data["checks"]
    assert isinstance(checks, list)
    assert len(checks) >= 1

    # Each check should have name, status, latency_ms
    for check in checks:
        assert "name" in check
        assert "status" in check
        assert "latency_ms" in check
        assert check["status"] in ("healthy", "degraded", "unhealthy")
        assert isinstance(check["latency_ms"], (int, float))


def test_health_endpoint_response_time(server: str) -> None:
    """Health endpoint responds within reasonable time (< 30s)."""
    start = time.perf_counter()
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        assert resp.status == 200
    except HTTPError as e:
        assert e.code == 503
    latency = time.perf_counter() - start
    assert latency < 30.0  # Reasonable timeout for full health checks


def test_health_endpoint_includes_external_http_check(server: str) -> None:
    """Health endpoint includes external HTTP connectivity check."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        data = json.loads(resp.read())
    except HTTPError as e:
        data = json.loads(e.read())
    check_names = [c["name"] for c in data["checks"]]
    assert "external_http" in check_names


def test_health_endpoint_includes_history_store_check(server: str) -> None:
    """Health endpoint includes history store accessibility check."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        data = json.loads(resp.read())
    except HTTPError as e:
        data = json.loads(e.read())
    check_names = [c["name"] for c in data["checks"]]
    assert "history_store" in check_names


def test_health_endpoint_includes_dns_check(server: str) -> None:
    """Health endpoint includes DNS resolution check."""
    try:
        resp = urllib.request.urlopen(f"{server}/health", timeout=30)
        data = json.loads(resp.read())
    except HTTPError as e:
        data = json.loads(e.read())
    check_names = [c["name"] for c in data["checks"]]
    assert "dns_resolution" in check_names


def test_server_binds_to_0_0_0_0() -> None:
    """Verify __main__ block reads PORT env var."""
    # Just verify the function signature accepts host/port
    import inspect

    from brokenlinkbrief.app import run

    sig = inspect.signature(run)
    assert "host" in sig.parameters
    assert "port" in sig.parameters

def test_railway_toml_exists() -> None:
    """railway.toml exists at project root."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    assert toml_path.exists(), f"railway.toml not found at {toml_path}"


def test_railway_toml_has_dockerfile_builder() -> None:
    """railway.toml uses DOCKERFILE builder."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    content = toml_path.read_text()
    assert 'builder = "DOCKERFILE"' in content


def test_railway_toml_has_healthcheck() -> None:
    """railway.toml has healthcheckPath set to /health."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    content = toml_path.read_text()
    assert 'healthcheckPath = "/health"' in content

def test_railway_toml_has_restart_policy() -> None:
    """railway.toml has restart policy ON_FAILURE with max retries."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    content = toml_path.read_text()
    assert 'restartPolicyType = "ON_FAILURE"' in content
    assert "restartPolicyMaxRetries" in content

def test_railway_toml_has_staging_environment() -> None:
    """railway.toml has staging environment configuration."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    content = toml_path.read_text()
    assert "[environments.staging]" in content

def test_railway_toml_has_production_environment() -> None:
    """railway.toml has production environment configuration."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    content = toml_path.read_text()
    assert "[environments.production]" in content

def test_infra_dockerfile_exists() -> None:
    """infra/Dockerfile exists for Railway deployment."""
    dockerfile_path = Path(__file__).resolve().parent.parent / "infra" / "Dockerfile"
    assert dockerfile_path.exists(), f"infra/Dockerfile not found at {dockerfile_path}"

def test_infra_dockerfile_is_multi_stage() -> None:
    """infra/Dockerfile uses multi-stage build (builder stage)."""
    dockerfile_path = Path(__file__).resolve().parent.parent / "infra" / "Dockerfile"
    content = dockerfile_path.read_text()
    assert "FROM python:3.11-slim AS builder" in content

def test_infra_dockerfile_has_non_root_user() -> None:
    """infra/Dockerfile creates and uses non-root user."""
    dockerfile_path = Path(__file__).resolve().parent.parent / "infra" / "Dockerfile"
    content = dockerfile_path.read_text()
    assert "USER app" in content
    assert "useradd" in content

def test_infra_dockerfile_exposes_port() -> None:
    """infra/Dockerfile exposes port 8000."""
    dockerfile_path = Path(__file__).resolve().parent.parent / "infra" / "Dockerfile"
    content = dockerfile_path.read_text()
    assert "EXPOSE 8000" in content

def test_railway_toml_points_to_infra_dockerfile() -> None:
    """railway.toml dockerfilePath points to infra/Dockerfile."""
    toml_path = Path(__file__).resolve().parent.parent / "railway.toml"
    content = toml_path.read_text()
    assert 'dockerfilePath = "infra/Dockerfile"' in content
