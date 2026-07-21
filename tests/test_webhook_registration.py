"""Pre-development interface/behavior tests for BrokenLinkBrief webhook registration.

Feature under test: ``POST /webhooks`` must accept a JSON body with a URL,
validate it against SSRF rules, and return a registration object.

State at authoring time (pre-tester, t_42a2d5a3):
- ``do_POST`` does NOT yet exist on ``_Handler`` in
  ``brokenlinkbrief.app`` (only ``do_GET`` is implemented).
- ``validate_webhook_url`` and ``WebhookRegistry`` ARE implemented in
  ``brokenlinkbrief.webhook``.
- Therefore interface tests for ``do_POST`` existence and behavioral
  tests for the HTTP endpoint are expected to FAIL until the developer
  adds ``do_POST`` to ``_Handler``.
- Unit-level tests against ``WebhookRegistry`` directly should PASS.
"""
from __future__ import annotations

import http.client
import inspect
import json
import socket
import threading
from http.server import HTTPServer

import pytest

from brokenlinkbrief.app import _Handler
from brokenlinkbrief.webhook import WebhookRegistry

# ---------------------------------------------------------------------------
# Interface tests — check structural existence.
# ---------------------------------------------------------------------------

def test_interface_handler_has_do_post() -> None:
    """_Handler must expose a do_POST method for POST /webhooks."""
    assert callable(getattr(_Handler, "do_POST", None))


def test_interface_webhook_registry_importable() -> None:
    """WebhookRegistry must be importable from the webhook module."""
    assert callable(WebhookRegistry)


def test_interface_webhook_registry_has_register() -> None:
    """WebhookRegistry must have a register method."""
    registry = WebhookRegistry()
    assert callable(getattr(registry, "register", None))


def test_interface_webhook_registry_register_signature() -> None:
    """register(url, secret=None) -> WebhookRegistration"""
    registry = WebhookRegistry()
    sig = inspect.signature(registry.register)
    params = list(sig.parameters.values())
    assert len(params) >= 1
    assert params[0].name == "url"


# ---------------------------------------------------------------------------
# Behavioral tests — WebhookRegistry unit level (should PASS).
# ---------------------------------------------------------------------------

def test_behavior_register_valid_https_url() -> None:
    """Registering a valid HTTPS URL must succeed and return a registration."""
    registry = WebhookRegistry()
    reg = registry.register("https://example.com/webhook")
    assert reg.url == "https://example.com/webhook"
    assert reg.id is not None
    assert len(reg.id) > 0


def test_behavior_register_stores_webhook() -> None:
    """A registered webhook must be retrievable by id."""
    registry = WebhookRegistry()
    reg = registry.register("https://example.com/webhook")
    fetched = registry.get(reg.id)
    assert fetched is not None
    assert fetched.url == "https://example.com/webhook"


def test_behavior_register_rejects_private_ip() -> None:
    """Registering a URL pointing to a private IP must raise ValueError."""
    registry = WebhookRegistry()
    with pytest.raises(ValueError, match="private|blocked"):
        registry.register("https://10.0.0.1/webhook")


def test_behavior_register_rejects_http_scheme() -> None:
    """Registering an HTTP (non-TLS) URL must raise ValueError."""
    registry = WebhookRegistry()
    with pytest.raises(ValueError):
        registry.register("http://example.com/webhook")


def test_behavior_register_rejects_file_scheme() -> None:
    """Registering a file:// URL must raise ValueError."""
    registry = WebhookRegistry()
    with pytest.raises(ValueError):
        registry.register("file:///etc/passwd")


def test_behavior_register_optional_secret() -> None:
    """The secret parameter must be optional and stored on the registration."""
    registry = WebhookRegistry()
    reg = registry.register("https://example.com/webhook", secret="s3cret")
    assert reg.secret == "s3cret"


def test_behavior_list_all_returns_all_registrations() -> None:
    """list_all() must return every registered webhook."""
    registry = WebhookRegistry()
    registry.register("https://a.example.com/webhook")
    registry.register("https://b.example.com/webhook")
    all_webhooks = registry.list_all()
    assert len(all_webhooks) == 2


def test_behavior_remove_deletes_registration() -> None:
    """remove(id) must delete the webhook and return True."""
    registry = WebhookRegistry()
    reg = registry.register("https://example.com/webhook")
    assert registry.remove(reg.id) is True
    assert registry.get(reg.id) is None


def test_behavior_remove_nonexistent_returns_false() -> None:
    """remove(id) for a non-existent id must return False."""
    registry = WebhookRegistry()
    assert registry.remove("nonexistent") is False


# ---------------------------------------------------------------------------
# Behavioral tests — HTTP endpoint (expect FAIL until do_POST is added).
# ---------------------------------------------------------------------------

def _start_server(monkeypatch):  # noqa: D401
    """Helper: start a temp server with token auth enabled."""
    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
    # Clear the module-level registry so tests don't leak state.
    from brokenlinkbrief.app import _webhook_registry

    _webhook_registry.clear()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_behavior_post_webhooks_valid_url_returns_201() -> None:
    """POST /webhooks with a valid HTTPS URL must return 201."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"url": "https://example.com/webhook"})
        conn.request(
            "POST",
            "/webhooks",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
        )
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
        conn.close()
        assert resp.status == 201, f"Expected 201, got {resp.status}: {resp_body}"
        data = json.loads(resp_body)
        assert "id" in data
        assert data["url"] == "https://example.com/webhook"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_post_webhooks_http_url_returns_400() -> None:
    """POST /webhooks with an HTTP URL must return 400."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"url": "http://example.com/webhook"})
        conn.request(
            "POST",
            "/webhooks",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 400, f"Expected 400 for HTTP URL, got {resp.status}"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_post_webhooks_private_ip_returns_400() -> None:
    """POST /webhooks with a private IP URL must return 400."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"url": "https://10.0.0.1/webhook"})
        conn.request(
            "POST",
            "/webhooks",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 400, f"Expected 400 for private IP, got {resp.status}"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_post_webhooks_invalid_json_returns_400() -> None:
    """POST /webhooks with malformed JSON must return 400."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/webhooks",
            body="not json",
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 400, f"Expected 400 for invalid JSON, got {resp.status}"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_post_webhooks_auth_required() -> None:
    """POST /webhooks must require auth when BROKENLINKBRIEF_SCAN_TOKEN is set."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"url": "https://example.com/webhook"})
        conn.request(
            "POST",
            "/webhooks",
            body=body,
            headers={
                "Host": "127.0.0.1",
                "Content-Type": "application/json",
                # No Authorization header
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 401, f"Expected 401 without auth, got {resp.status}"
    finally:
        server.shutdown()
        monkeypatch.undo()


def test_behavior_post_webhooks_duplicate_url_returns_409() -> None:
    """POST /webhooks with a duplicate URL must return 409."""
    monkeypatch = pytest.MonkeyPatch()
    server, port = _start_server(monkeypatch)
    try:
        payload = json.dumps({"url": "https://example.com/webhook"})
        headers = {
            "Host": "127.0.0.1",
            "Content-Type": "application/json",
            "Authorization": "Bearer secret",
        }
        # First registration
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/webhooks", body=payload, headers=headers)
        resp1 = conn.getresponse()
        resp1.read()
        conn.close()
        assert resp1.status == 201

        # Duplicate registration
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/webhooks", body=payload, headers=headers)
        resp2 = conn.getresponse()
        resp2.read()
        conn.close()
        assert resp2.status == 409, (
            f"Expected 409 for duplicate URL, got {resp2.status}"
        )
    finally:
        server.shutdown()
        monkeypatch.undo()
