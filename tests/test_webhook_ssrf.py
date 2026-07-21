"""Pre-development interface/behavior tests for BrokenLinkBrief SSRF validation.

Feature under test: ``validate_webhook_url(url)`` in
``brokenlinkbrief.webhook`` must reject private/loopback IPs, non-HTTPS
schemes, and other unsafe URLs.

State at authoring time (pre-tester, t_42a2d5a3):
- ``validate_webhook_url`` IS implemented in ``brokenlinkbrief.webhook``.
- Therefore interface AND behavioral tests are expected to PASS immediately.
"""
from __future__ import annotations

import inspect

import pytest

from brokenlinkbrief.webhook import validate_webhook_url

# ---------------------------------------------------------------------------
# Interface tests — these MUST pass immediately.
# ---------------------------------------------------------------------------

def test_interface_validate_webhook_url_importable() -> None:
    """validate_webhook_url must be importable from the webhook module."""
    assert callable(validate_webhook_url)


def test_interface_validate_webhook_url_signature_matches_contract() -> None:
    """validate_webhook_url(url: str) -> str | None"""
    signature = inspect.signature(validate_webhook_url)
    params = list(signature.parameters.values())
    assert len(params) == 1
    assert params[0].name == "url"
    # Return annotation should be str | None (or Optional[str])
    ret = str(signature.return_annotation)
    assert "str" in ret and ("None" in ret or "Optional" in ret)


# ---------------------------------------------------------------------------
# Behavioral tests — blocking private / loopback IPs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/webhook",
        "https://127.0.0.2/webhook",
        "https://127.255.255.255/webhook",
    ],
    ids=["127.0.0.1", "127.0.0.2", "127.255.255.255"],
)
def test_behavior_blocks_loopback_127(url: str) -> None:
    """127.0.0.0/8 addresses must be rejected."""
    error = validate_webhook_url(url)
    assert error is not None
    assert "private" in error.lower() or "blocked" in error.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.1/webhook",
        "https://10.255.255.255/webhook",
        "https://10.1.2.3/webhook",
    ],
    ids=["10.0.0.1", "10.255.255.255", "10.1.2.3"],
)
def test_behavior_blocks_private_10(url: str) -> None:
    """10.0.0.0/8 addresses must be rejected."""
    error = validate_webhook_url(url)
    assert error is not None
    assert "private" in error.lower() or "blocked" in error.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://172.16.0.1/webhook",
        "https://172.31.255.255/webhook",
        "https://172.20.10.5/webhook",
    ],
    ids=["172.16.0.1", "172.31.255.255", "172.20.10.5"],
)
def test_behavior_blocks_private_172(url: str) -> None:
    """172.16.0.0/12 addresses must be rejected."""
    error = validate_webhook_url(url)
    assert error is not None
    assert "private" in error.lower() or "blocked" in error.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://192.168.0.1/webhook",
        "https://192.168.1.100/webhook",
        "https://192.168.255.255/webhook",
    ],
    ids=["192.168.0.1", "192.168.1.100", "192.168.255.255"],
)
def test_behavior_blocks_private_192(url: str) -> None:
    """192.168.0.0/16 addresses must be rejected."""
    error = validate_webhook_url(url)
    assert error is not None
    assert "private" in error.lower() or "blocked" in error.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.0.1/webhook",
        "https://169.254.169.254/webhook",
    ],
    ids=["169.254.0.1", "169.254.169.254"],
)
def test_behavior_blocks_link_local_169(url: str) -> None:
    """169.254.0.0/16 (link-local / metadata) addresses must be rejected."""
    error = validate_webhook_url(url)
    assert error is not None


# ---------------------------------------------------------------------------
# Behavioral tests — blocking non-HTTPS schemes
# ---------------------------------------------------------------------------

def test_behavior_blocks_http_scheme() -> None:
    """HTTP (non-TLS) URLs must be rejected."""
    error = validate_webhook_url("http://example.com/webhook")
    assert error is not None
    assert "https" in error.lower() or "scheme" in error.lower()


def test_behavior_allows_https_scheme() -> None:
    """HTTPS URLs with a public hostname must be allowed."""
    error = validate_webhook_url("https://example.com/webhook")
    assert error is None


# ---------------------------------------------------------------------------
# Behavioral tests — blocking non-http(s) schemes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/webhook",
        "gopher://example.com/webhook",
        "javascript:alert(1)",
    ],
    ids=["file", "ftp", "gopher", "javascript"],
)
def test_behavior_blocks_non_http_schemes(url: str) -> None:
    """Only http and https schemes should be allowed."""
    error = validate_webhook_url(url)
    assert error is not None


# ---------------------------------------------------------------------------
# Behavioral tests — edge cases
# ---------------------------------------------------------------------------

def test_behavior_blocks_missing_hostname() -> None:
    """URLs without a hostname must be rejected."""
    error = validate_webhook_url("https:///webhook")
    assert error is not None


def test_behavior_blocks_localhost_hostname() -> None:
    """The literal hostname 'localhost' must be rejected."""
    error = validate_webhook_url("https://localhost/webhook")
    assert error is not None


def test_behavior_blocks_0_0_0_0() -> None:
    """0.0.0.0 must be rejected."""
    error = validate_webhook_url("https://0.0.0.0/webhook")
    assert error is not None
