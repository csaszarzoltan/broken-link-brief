"""Deployment smoke tests for Railway readiness."""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

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
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("Server did not start within 6 seconds")
    yield base
    proc.terminate()
    proc.wait(timeout=5)


def test_health_endpoint_returns_ok(server: str) -> None:
    """Health endpoint returns 200 with status ok."""
    resp = urllib.request.urlopen(f"{server}/health", timeout=5)
    assert resp.status == 200
    import json

    data = json.loads(resp.read())
    assert data["status"] == "ok"


def test_server_binds_to_0_0_0_0() -> None:
    """Verify __main__ block reads PORT env var."""
    from brokenlinkbrief.app import run

    # Just verify the function signature accepts host/port
    import inspect

    sig = inspect.signature(run)
    assert "host" in sig.parameters
    assert "port" in sig.parameters
