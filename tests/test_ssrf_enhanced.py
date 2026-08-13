"""Tests for the enhanced SSRF protection (ReceiptLens pattern transfer).

Tests the DNS resolution validation, hostname substring blocking,
and comprehensive reserved network range checks added to validate_scan_url.
"""

from __future__ import annotations

from unittest.mock import patch

from brokenlinkbrief.package import validate_scan_url

# ---------------------------------------------------------------------------
# Hostname substring blocking
# ---------------------------------------------------------------------------


def test_blocks_localhost_substring() -> None:
    """Hostnames ending in .local must be blocked."""
    result = validate_scan_url("http://myhost.local")
    assert result is not None
    assert "blocked" in result.lower() or "local" in result.lower()


def test_blocks_internal_substring() -> None:
    """Hostnames ending in .internal must be blocked."""
    result = validate_scan_url("http://service.internal")
    assert result is not None
    assert "blocked" in result.lower() or "internal" in result.lower()


def test_blocks_exact_metadata() -> None:
    """The bare hostname 'metadata' must be blocked."""
    result = validate_scan_url("http://metadata")
    assert result is not None


# ---------------------------------------------------------------------------
# DNS resolution + reserved IP validation
# ---------------------------------------------------------------------------


def _fake_getaddrinfo_reserved(host, port=None):
    """Simulate a hostname that resolves to a private IP."""
    return [(2, 1, 6, "", ("10.0.0.99", 0))]


def _fake_getaddrinfo_public(host, port=None):
    """Simulate a hostname that resolves to a public IP."""
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def test_dns_rebinding_blocked_private() -> None:
    """Domain resolving to a private IP must be blocked."""
    with patch("socket.getaddrinfo", _fake_getaddrinfo_reserved):
        result = validate_scan_url("https://evil.example.com")
    assert result is not None
    assert "reserved" in result.lower() or "private" in result.lower()


def test_dns_resolves_public_allowed() -> None:
    """Domain resolving to a public IP must be allowed."""
    with patch("socket.getaddrinfo", _fake_getaddrinfo_public):
        result = validate_scan_url("https://example.com")
    assert result is None


def test_dns_resolution_failure_allowed() -> None:
    """Unresolvable hostnames should not block (host may be temporarily dead)."""

    def _fail_getaddrinfo(host, port=None):
        raise OSError("Name or service not known")

    with patch("socket.getaddrinfo", _fail_getaddrinfo):
        result = validate_scan_url("https://nonexistent.example.com")
    assert result is None


# ---------------------------------------------------------------------------
# Comprehensive reserved network ranges
# ---------------------------------------------------------------------------


def test_blocks_multicast_ip() -> None:
    """Multicast IPs (224.0.0.0/4) must be blocked."""
    result = validate_scan_url("http://224.0.0.1")
    assert result is not None


def test_blocks_reserved_ip_range() -> None:
    """Reserved IPs (240.0.0.0/4) must be blocked."""
    result = validate_scan_url("http://240.0.0.1")
    assert result is not None


def test_blocks_cgnat_ip() -> None:
    """CGNAT IPs (100.64.0.0/10) must be blocked."""
    result = validate_scan_url("http://100.64.0.1")
    assert result is not None


# ---------------------------------------------------------------------------
# Existing behavior preserved
# ---------------------------------------------------------------------------


def test_allows_public_http() -> None:
    """Public HTTP URLs should still be allowed."""
    assert validate_scan_url("http://example.com") is None


def test_allows_public_https() -> None:
    """Public HTTPS URLs should still be allowed."""
    assert validate_scan_url("https://example.com") is None


def test_blocks_loopback() -> None:
    """Loopback addresses must still be blocked."""
    result = validate_scan_url("http://127.0.0.1")
    assert result is not None


def test_blocks_private_10() -> None:
    """10.0.0.0/8 must still be blocked."""
    result = validate_scan_url("http://10.0.0.1")
    assert result is not None


def test_blocks_invalid_url() -> None:
    """Invalid URLs must still be blocked."""
    result = validate_scan_url("not-a-url")
    assert result is not None
