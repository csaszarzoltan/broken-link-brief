"""Behavioral and interface tests for the webhook notification feature.

Interface tests verify that the required functions/classes exist with correct
signatures and return types.  Behavioral tests exercise the actual logic
(HMAC signing, retry, delivery, registration, SSRF rejection).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from unittest.mock import patch

import pytest

from brokenlinkbrief.package import LinkResult
from brokenlinkbrief.webhook import (
    WebhookRegistry,
    build_payload,
    deliver_webhook,
    deliver_with_retry,
    sign_payload,
    trigger_webhooks,
    validate_webhook_url,
    verify_signature,
)

# ═══════════════════════════════════════════════════════════════════════════
# Interface tests — must pass immediately
# ═══════════════════════════════════════════════════════════════════════════


class TestInterface:
    """Verify required functions and classes exist with correct signatures."""

    def test_sign_payload_exists_and_returns_str(self) -> None:
        result = sign_payload(b"hello", "secret")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest

    def test_verify_signature_exists_and_returns_bool(self) -> None:
        sig = sign_payload(b"test", "s")
        result = verify_signature(b"test", "s", sig)
        assert isinstance(result, bool)

    def test_deliver_webhook_exists_and_returns_int(self) -> None:
        """deliver_webhook signature accepts url, payload, optional secret."""
        import inspect

        sig = inspect.signature(deliver_webhook)
        params = list(sig.parameters.keys())
        assert "url" in params
        assert "payload_bytes" in params
        assert "secret" in params

    def test_deliver_with_retry_exists(self) -> None:
        import inspect

        sig = inspect.signature(deliver_with_retry)
        params = list(sig.parameters.keys())
        assert "url" in params
        assert "payload_bytes" in params
        assert "secret" in params
        assert "max_attempts" in params

    def test_webhook_registry_exists(self) -> None:
        registry = WebhookRegistry()
        assert hasattr(registry, "register")
        assert hasattr(registry, "list_all")
        assert hasattr(registry, "get")

    def test_build_payload_exists_and_returns_bytes(self) -> None:
        results = [LinkResult(url="http://example.com", status=200, reason="OK")]
        payload = build_payload("http://test.com", results)
        assert isinstance(payload, bytes)

    def test_trigger_webhooks_exists(self) -> None:
        import inspect

        sig = inspect.signature(trigger_webhooks)
        params = list(sig.parameters.keys())
        assert "registry" in params
        assert "scanned_url" in params
        assert "results" in params

    def test_validate_webhook_url_exists(self) -> None:
        result = validate_webhook_url("https://example.com/hook")
        assert result is None  # None means valid


# ═══════════════════════════════════════════════════════════════════════════
# Behavioral tests — exercise actual logic
# ═══════════════════════════════════════════════════════════════════════════


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------


class TestHMACSigning:
    """Verify HMAC-SHA256 signing and verification."""

    def test_hmac_matches_known_digest(self) -> None:
        """X-Webhook-Signature must equal HMAC-SHA256(secret, payload)."""
        payload = b'{"scanned_url":"http://example.com"}'
        secret = "my-test-secret"
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        assert sign_payload(payload, secret) == expected

    def test_hmac_varies_with_secret(self) -> None:
        sig1 = sign_payload(b"data", "secret1")
        sig2 = sign_payload(b"data", "secret2")
        assert sig1 != sig2

    def test_hmac_varies_with_payload(self) -> None:
        sig1 = sign_payload(b"payload-a", "secret")
        sig2 = sign_payload(b"payload-b", "secret")
        assert sig1 != sig2

    def test_verify_signature_valid(self) -> None:
        sig = sign_payload(b"hello", "key")
        assert verify_signature(b"hello", "key", sig) is True

    def test_verify_signature_invalid(self) -> None:
        assert verify_signature(b"hello", "key", "deadbeef" * 8) is False

    def test_signature_is_hex_string(self) -> None:
        sig = sign_payload(b"test", "s")
        # SHA-256 hex digest is 64 hex chars
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)


# ---------------------------------------------------------------------------
# Webhook registration
# ---------------------------------------------------------------------------


class TestWebhookRegistration:
    """Verify webhook registration stores URL + secret and rejects bad URLs."""

    def test_register_returns_registration_id(self) -> None:
        registry = WebhookRegistry()
        reg = registry.register("https://example.com/hook")
        assert reg.id
        assert reg.url == "https://example.com/hook"

    def test_register_stores_optional_secret(self) -> None:
        registry = WebhookRegistry()
        reg = registry.register("https://example.com/hook", secret="s3cret")
        assert reg.secret == "s3cret"

    def test_register_stores_none_secret_by_default(self) -> None:
        registry = WebhookRegistry()
        reg = registry.register("https://example.com/hook")
        assert reg.secret is None

    def test_list_all_returns_registered_webhooks(self) -> None:
        registry = WebhookRegistry()
        registry.register("https://a.example.com")
        registry.register("https://b.example.com")
        assert len(registry.list_all()) == 2

    def test_get_returns_registration_by_id(self) -> None:
        registry = WebhookRegistry()
        reg = registry.register("https://example.com/hook")
        fetched = registry.get(reg.id)
        assert fetched is not None
        assert fetched.url == "https://example.com/hook"

    def test_remove_deletes_registration(self) -> None:
        registry = WebhookRegistry()
        reg = registry.register("https://example.com/hook")
        assert registry.remove(reg.id) is True
        assert registry.get(reg.id) is None

    def test_remove_nonexistent_returns_false(self) -> None:
        registry = WebhookRegistry()
        assert registry.remove("nope") is False


# ---------------------------------------------------------------------------
# SSRF protection for webhook URLs
# ---------------------------------------------------------------------------


class TestSSRFProtection:
    """Verify webhook URLs that point to private/internal hosts are rejected."""

    def test_rejects_localhost(self) -> None:
        with pytest.raises(ValueError, match="blocked host"):
            WebhookRegistry().register("http://localhost/hook")

    def test_rejects_127_0_0_1(self) -> None:
        with pytest.raises(ValueError, match="blocked host"):
            WebhookRegistry().register("http://127.0.0.1/hook")

    def test_rejects_private_ip(self) -> None:
        with pytest.raises(ValueError, match="private IP"):
            WebhookRegistry().register("http://192.168.1.1/hook")

    def test_rejects_link_local(self) -> None:
        with pytest.raises(ValueError, match="private IP"):
            WebhookRegistry().register("http://10.0.0.1/hook")

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ValueError, match="only HTTPS"):
            WebhookRegistry().register("ftp://example.com/hook")

    def test_accepts_public_https(self) -> None:
        reg = WebhookRegistry().register("https://hooks.example.com/notify")
        assert reg.url == "https://hooks.example.com/notify"


# ---------------------------------------------------------------------------
# Payload schema
# ---------------------------------------------------------------------------


class TestPayloadSchema:
    """Verify webhook payload contains required fields."""

    def test_payload_has_scanned_url(self) -> None:
        results = [LinkResult(url="http://a.com", status=200, reason="OK")]
        payload = json.loads(build_payload("http://target.com", results))
        assert payload["scanned_url"] == "http://target.com"

    def test_payload_has_broken_links_list(self) -> None:
        results = [
            LinkResult(url="http://ok.com", status=200, reason="OK"),
            LinkResult(url="http://broken.com", status=404, reason="Not Found"),
        ]
        payload = json.loads(build_payload("http://target.com", results))
        assert isinstance(payload["broken_links"], list)
        assert len(payload["broken_links"]) == 1
        assert payload["broken_links"][0]["url"] == "http://broken.com"

    def test_payload_has_timestamp(self) -> None:
        results = [LinkResult(url="http://a.com", status=200, reason="OK")]
        payload = json.loads(build_payload("http://target.com", results))
        assert "timestamp" in payload
        # Should be a valid ISO timestamp
        from datetime import datetime

        datetime.fromisoformat(payload["timestamp"])

    def test_payload_has_total_links(self) -> None:
        results = [
            LinkResult(url=f"http://a{i}.com", status=200, reason="OK")
            for i in range(5)
        ]
        payload = json.loads(build_payload("http://target.com", results))
        assert payload["total_links"] == 5

    def test_broken_link_includes_status_and_reason(self) -> None:
        results = [
            LinkResult(
                url="http://broken.com",
                status=500,
                reason="Internal Server Error",
            )
        ]
        payload = json.loads(build_payload("http://target.com", results))
        bl = payload["broken_links"][0]
        assert bl["status"] == 500
        assert bl["reason"] == "Internal Server Error"


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------


def _make_test_server() -> tuple[HTTPServer, int, list[dict[str, Any]]]:
    """Create a lightweight HTTP server that captures POST requests."""
    received: list[dict[str, Any]] = []

    class CapturingHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b""
            received.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )
            self.send_response(200)
            self.end_headers()

        def log_message(self, message: str, *args: Any) -> None:
            return  # silence logging

    server = HTTPServer(("127.0.0.1", 0), CapturingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, received


class TestWebhookDelivery:
    """Verify webhook delivery sends POST with correct headers."""

    @patch("brokenlinkbrief.webhook.validate_webhook_url", return_value=None)
    def test_delivers_payload_to_url(self, mock_validate) -> None:
        server, port, received = _make_test_server()
        try:
            url = f"http://127.0.0.1:{port}/hook"
            payload = b'{"test": true}'
            status = deliver_webhook(url, payload)
            assert status == 200
            assert len(received) == 1
            assert received[0]["body"] == payload
        finally:
            server.shutdown()

    @patch("brokenlinkbrief.webhook.validate_webhook_url", return_value=None)
    def test_delivers_with_signature_header(self, mock_validate) -> None:
        server, port, received = _make_test_server()
        try:
            url = f"http://127.0.0.1:{port}/hook"
            payload = b'{"test": true}'
            secret = "my-secret"
            deliver_webhook(url, payload, secret=secret)
            sig_header = received[0]["headers"].get("X-Webhook-Signature", "")
            expected = sign_payload(payload, secret)
            assert sig_header == expected
        finally:
            server.shutdown()

    @patch("brokenlinkbrief.webhook.validate_webhook_url", return_value=None)
    def test_content_type_is_json(self, mock_validate) -> None:
        server, port, received = _make_test_server()
        try:
            url = f"http://127.0.0.1:{port}/hook"
            deliver_webhook(url, b"{}")
            ct = received[0]["headers"].get("Content-Type", "")
            assert ct == "application/json"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Verify exponential-backoff retry on delivery failure."""

    @patch("brokenlinkbrief.webhook.validate_webhook_url", return_value=None)
    def test_succeeds_on_first_attempt(self, mock_validate) -> None:
        server, port, _ = _make_test_server()
        try:
            url = f"http://127.0.0.1:{port}/hook"
            status = deliver_with_retry(url, b"{}", max_attempts=3, base_delay=0.01)
            assert status == 200
        finally:
            server.shutdown()

    def test_retries_on_failure_then_succeeds(self) -> None:
        """First call fails, second succeeds (simulated via mock)."""
        call_count = 0

        def mock_deliver(url, payload, secret=None, timeout=10.0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("connection refused")
            return 200

        with patch("brokenlinkbrief.webhook.deliver_webhook", side_effect=mock_deliver):
            status = deliver_with_retry(
                "http://example.com/hook",
                b"{}",
                max_attempts=3,
                base_delay=0.01,
            )
            assert status == 200
            assert call_count == 2

    def test_gives_up_after_max_attempts(self) -> None:
        with (
            patch(
                "brokenlinkbrief.webhook.deliver_webhook",
                side_effect=ConnectionError("always fails"),
            ),
            pytest.raises(RuntimeError, match="failed after 3 attempts"),
        ):
            deliver_with_retry(
                "http://example.com/hook",
                b"{}",
                max_attempts=3,
                base_delay=0.01,
            )

    def test_exponential_backoff_delays(self) -> None:
        """Verify delays increase: 1s, 2s, 4s (with base_delay=1.0)."""
        delays: list[float] = []

        def mock_deliver(url, payload, secret=None, timeout=10.0):
            raise ConnectionError("fail")

        def track_sleep(seconds: float) -> None:
            delays.append(seconds)

        with (
            patch("brokenlinkbrief.webhook.deliver_webhook", side_effect=mock_deliver),
            patch("brokenlinkbrief.webhook.time.sleep", side_effect=track_sleep),
        ):
            with pytest.raises(RuntimeError):
                deliver_with_retry(
                    "http://example.com/hook",
                    b"{}",
                    max_attempts=3,
                    base_delay=1.0,
                )
            # 2 delays (no sleep after last failure)
            assert delays == [1.0, 2.0]

    def test_attempt_count_respected(self) -> None:
        call_count = 0

        def mock_deliver(url, payload, secret=None, timeout=10.0):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with patch("brokenlinkbrief.webhook.deliver_webhook", side_effect=mock_deliver):
            with pytest.raises(RuntimeError):
                deliver_with_retry(
                    "http://example.com/hook",
                    b"{}",
                    max_attempts=5,
                    base_delay=0.01,
                )
            assert call_count == 5


# ---------------------------------------------------------------------------
# Trigger: notification after scan with broken links
# ---------------------------------------------------------------------------


@patch("brokenlinkbrief.webhook.validate_webhook_url", return_value=None)
class TestTriggerWebhooks:
    """Verify trigger_webhooks fires only when broken links are found."""

    def test_fires_when_broken_links_found(self, mock_validate) -> None:
        server, port, received = _make_test_server()
        try:
            registry = WebhookRegistry()
            registry.register(f"http://127.0.0.1:{port}/hook", skip_validation=True)
            results = [
                LinkResult(url="http://ok.com", status=200, reason="OK"),
                LinkResult(url="http://broken.com", status=404, reason="Not Found"),
            ]
            outcomes = trigger_webhooks(registry, "http://target.com", results)
            assert len(outcomes) == 1
            assert outcomes[0]["status"] == "ok"
            assert len(received) == 1
        finally:
            server.shutdown()

    def test_does_not_fire_when_no_broken_links(self, mock_validate) -> None:
        server, port, received = _make_test_server()
        try:
            registry = WebhookRegistry()
            registry.register(f"http://127.0.0.1:{port}/hook", skip_validation=True)
            results = [
                LinkResult(url="http://ok.com", status=200, reason="OK"),
                LinkResult(url="http://ok2.com", status=200, reason="OK"),
            ]
            outcomes = trigger_webhooks(registry, "http://target.com", results)
            assert outcomes == []
            assert len(received) == 0
        finally:
            server.shutdown()

    def test_fires_to_multiple_webhooks(self, mock_validate) -> None:
        server1, port1, received1 = _make_test_server()
        server2, port2, received2 = _make_test_server()
        try:
            registry = WebhookRegistry()
            registry.register(f"http://127.0.0.1:{port1}/hook", skip_validation=True)
            registry.register(f"http://127.0.0.1:{port2}/hook", skip_validation=True)
            results = [
                LinkResult(url="http://broken.com", status=500, reason="Server Error"),
            ]
            outcomes = trigger_webhooks(registry, "http://target.com", results)
            assert len(outcomes) == 2
            assert len(received1) == 1
            assert len(received2) == 1
        finally:
            server1.shutdown()
            server2.shutdown()

    def test_payload_sent_includes_hmac_when_secret_set(self, mock_validate) -> None:
        server, port, received = _make_test_server()
        try:
            secret = "test-secret-123"
            registry = WebhookRegistry()
            url = f"http://127.0.0.1:{port}/hook"
            registry.register(url, secret=secret, skip_validation=True)
            results = [
                LinkResult(url="http://broken.com", status=404, reason="Not Found"),
            ]
            trigger_webhooks(registry, "http://target.com", results)
            sig = received[0]["headers"].get("X-Webhook-Signature", "")
            assert sig  # non-empty
            body = received[0]["body"]
            expected = sign_payload(body, secret)
            assert sig == expected
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Payload contains broken links only
# ---------------------------------------------------------------------------


class TestPayloadBrokenLinksOnly:
    """Verify only broken links appear in the webhook payload."""

    def test_only_broken_links_in_payload(self) -> None:
        results = [
            LinkResult(url="http://ok1.com", status=200, reason="OK"),
            LinkResult(url="http://ok2.com", status=301, reason="Moved"),
            LinkResult(url="http://broken.com", status=404, reason="Not Found"),
            LinkResult(url="http://timeout.com", status=None, reason="timeout"),
        ]
        payload = json.loads(build_payload("http://target.com", results))
        urls = [bl["url"] for bl in payload["broken_links"]]
        assert "http://ok1.com" not in urls
        assert "http://ok2.com" not in urls
        assert "http://broken.com" in urls
        assert "http://timeout.com" in urls

    def test_empty_results_gives_empty_broken_links(self) -> None:
        payload = json.loads(build_payload("http://target.com", []))
        assert payload["broken_links"] == []
        assert payload["total_links"] == 0
