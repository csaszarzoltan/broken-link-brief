"""Webhook notification system for BrokenLinkBrief.

Provides webhook registration, HMAC-SHA256 signed delivery,
and retry logic for notifying external systems when broken
links are detected during scans.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from brokenlinkbrief.package import LinkResult

# ---------------------------------------------------------------------------
# SSRF protection for webhook URLs
# ---------------------------------------------------------------------------

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "169.254.169.254",
    }
)


def _is_private_ip(hostname: str) -> bool:
    """Return True if *hostname* looks like a private / loopback address."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


def validate_webhook_url(url: str) -> str | None:
    """Validate a webhook URL against basic SSRF rules.

    Returns ``None`` when the URL is allowed, or a human-readable error
    string when it must be rejected.

    Host/scheme checks are ordered so that dangerous hosts are caught
    regardless of the scheme — an ``http://localhost`` URL should still
    be flagged as a blocked host, not merely as a scheme violation.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid URL"

    hostname = parsed.hostname or ""
    if not hostname:
        return "missing hostname"

    if hostname.lower() in _BLOCKED_HOSTS:
        return f"blocked host: {hostname}"

    if _is_private_ip(hostname):
        return f"private IP: {hostname}"

    if parsed.scheme != "https":
        return "only HTTPS URLs are allowed for webhooks"

    return None


# ---------------------------------------------------------------------------
# Webhook storage
# ---------------------------------------------------------------------------


@dataclass
class WebhookRegistration:
    """A registered webhook endpoint."""

    id: str
    url: str
    secret: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class WebhookRegistry:
    """In-memory webhook registration store."""

    def __init__(self) -> None:
        self._webhooks: dict[str, WebhookRegistration] = {}
        self._lock = threading.Lock()

    def register(
        self,
        url: str,
        secret: str | None = None,
        *,
        skip_validation: bool = False,
    ) -> WebhookRegistration:
        """Register a new webhook URL with an optional HMAC secret.

        Raises ``ValueError`` if the URL fails SSRF validation
        (unless *skip_validation* is True, for test use only).
        """
        if not skip_validation:
            error = validate_webhook_url(url)
            if error:
                raise ValueError(error)

        webhook_id = uuid.uuid4().hex[:12]
        reg = WebhookRegistration(id=webhook_id, url=url, secret=secret)
        with self._lock:
            self._webhooks[webhook_id] = reg
        return reg

    def get(self, webhook_id: str) -> WebhookRegistration | None:
        """Return a registration by id, or ``None``."""
        with self._lock:
            return self._webhooks.get(webhook_id)

    def list_all(self) -> list[WebhookRegistration]:
        """Return all registered webhooks."""
        with self._lock:
            return list(self._webhooks.values())

    def find_by_url(self, url: str) -> WebhookRegistration | None:
        """Return the first registration matching *url*, or ``None``."""
        with self._lock:
            for reg in self._webhooks.values():
                if reg.url == url:
                    return reg
            return None

    def clear(self) -> None:
        """Remove all registered webhooks (useful for test isolation)."""
        with self._lock:
            self._webhooks.clear()

    def remove(self, webhook_id: str) -> bool:
        """Remove a webhook by id.  Returns True if it existed."""
        with self._lock:
            return self._webhooks.pop(webhook_id, None) is not None


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------


def sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute an HMAC-SHA256 hex digest for *payload_bytes* using *secret*.

    Returns the hex-encoded signature string suitable for use in the
    ``X-Webhook-Signature`` header.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    payload_bytes: bytes,
    secret: str,
    signature: str,
) -> bool:
    """Timing-safe verification of an HMAC-SHA256 signature."""
    expected = sign_payload(payload_bytes, secret)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def deliver_webhook(
    url: str,
    payload_bytes: bytes,
    secret: str | None = None,
    timeout: float = 10.0,
) -> int:
    """POST *payload_bytes* to *url* with an optional HMAC signature header.

    Returns the HTTP status code on success.  Raises ``ConnectionError``
    or ``RuntimeError`` on failure so the caller can decide on retries.
    """
    error = validate_webhook_url(url)
    if error:
        raise ValueError(f"SSRF blocked: {error}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if secret:
        headers["X-Webhook-Signature"] = sign_payload(payload_bytes, secret)

    req = Request(url, data=payload_bytes, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise ConnectionError(str(exc.reason)) from exc


def deliver_with_retry(
    url: str,
    payload_bytes: bytes,
    secret: str | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    timeout: float = 10.0,
) -> int:
    """Deliver a webhook payload with exponential-backoff retry.

    Attempts up to *max_attempts* times with delays of
    ``base_delay * 2^(attempt-1)`` seconds between attempts.

    Returns the HTTP status code on the first successful delivery.
    Raises ``RuntimeError`` if all attempts fail.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return deliver_webhook(url, payload_bytes, secret, timeout)
        except (ConnectionError, RuntimeError) as exc:
            last_error = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                time.sleep(delay)
    raise RuntimeError(
        f"webhook delivery failed after {max_attempts} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Scan-result payload builder
# ---------------------------------------------------------------------------


def build_payload(
    scanned_url: str,
    results: list[LinkResult],
) -> bytes:
    """Build a JSON webhook payload from scan results.

    Returns UTF-8 encoded JSON bytes.
    """
    broken = [
        {
            "url": r.url,
            "status": r.status,
            "reason": r.reason,
        }
        for r in results
        if (r.status is not None and r.status >= 400)
        or (r.status is None and r.reason is not None)
    ]

    payload = {
        "scanned_url": scanned_url,
        "broken_links": broken,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_links": len(results),
    }
    return json.dumps(payload).encode("utf-8")


# ---------------------------------------------------------------------------
# Trigger: notify all registered webhooks
# ---------------------------------------------------------------------------


def trigger_webhooks(
    registry: WebhookRegistry,
    scanned_url: str,
    results: list[LinkResult],
) -> list[dict[str, Any]]:
    """Deliver scan results to all registered webhooks.

    Only fires when at least one broken link is found.

    Returns a list of delivery result dicts:
    ``{"webhook_id": ..., "url": ..., "status": "ok"|"error", "detail": ...}``
    """
    broken_count = sum(
        1
        for r in results
        if (r.status is not None and r.status >= 400)
        or (r.status is None and r.reason is not None)
    )
    if broken_count == 0:
        return []

    payload_bytes = build_payload(scanned_url, results)
    webhooks = registry.list_all()
    outcomes: list[dict[str, Any]] = []

    for wh in webhooks:
        try:
            deliver_with_retry(wh.url, payload_bytes, wh.secret)
            outcomes.append({"webhook_id": wh.id, "url": wh.url, "status": "ok"})
        except (ConnectionError, RuntimeError) as exc:
            outcomes.append(
                {
                    "webhook_id": wh.id,
                    "url": wh.url,
                    "status": "error",
                    "detail": str(exc),
                }
            )

    return outcomes
