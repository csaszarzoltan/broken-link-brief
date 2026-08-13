"""Central outbound crawl policy with SSRF and resource controls."""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


class PolicyViolation(ValueError):  # noqa: N818 — legacy public API name
    """Raised when a URL or redirect chain violates the crawl policy."""


# Backwards-compatible alias (legacy name referenced by tests and callers).
PolicyError = PolicyViolation


@dataclass(frozen=True)
class CrawlPolicy:
    """Constraints applied to every outbound crawl."""

    schemes: tuple[str, ...] = ("http", "https")
    max_redirects: int = 5
    max_response_bytes: int = 5_000_000
    allowed_ports: tuple[int, ...] = (80, 443)
    allow_private: bool = False


def _unsafe(ip: str) -> bool:
    """Return True for private, loopback, link-local, reserved or multicast IPs."""
    address = ipaddress.ip_address(ip)
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _is_ip(value: str) -> bool:
    """Return True when value parses as an IP address."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def validate_target(
    url: str,
    policy: CrawlPolicy,
    resolver=socket.getaddrinfo,
) -> tuple[str, ...]:
    """Validate a URL against the policy; returns the resolved addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in policy.schemes or not parsed.hostname:
        raise PolicyViolation("unsupported scheme or missing hostname")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in policy.allowed_ports:
        raise PolicyViolation("port is not allowed")
    try:
        if _is_ip(parsed.hostname):
            addresses = (parsed.hostname,)
        else:
            addresses = tuple(
                dict.fromkeys(
                    info[4][0]
                    for info in resolver(
                        parsed.hostname, port, type=socket.SOCK_STREAM
                    )
                )
            )
    except OSError as exc:
        raise PolicyViolation("DNS resolution failed") from exc
    if not addresses:
        raise PolicyViolation("DNS returned no addresses")
    if not policy.allow_private and any(_unsafe(a) for a in addresses):
        raise PolicyViolation("private or reserved destination blocked")
    return addresses


def validate_redirect_chain(
    urls: list[str],
    policy: CrawlPolicy,
    resolver=socket.getaddrinfo,
) -> None:
    """Validate every hop of a redirect chain against the policy."""
    if len(urls) - 1 > policy.max_redirects:
        raise PolicyViolation("redirect budget exceeded")
    for url in urls:
        validate_target(url, policy, resolver)
