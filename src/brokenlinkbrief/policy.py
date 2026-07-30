"""Central outbound crawl policy with SSRF and resource controls."""
from __future__ import annotations
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

class PolicyViolation(ValueError): pass
@dataclass(frozen=True)
class CrawlPolicy:
    schemes: tuple[str,...]=("http","https")
    max_redirects: int=5
    max_response_bytes: int=5_000_000
    allowed_ports: tuple[int,...]=(80,443)
    allow_private: bool=False

def _unsafe(ip: str) -> bool:
    a=ipaddress.ip_address(ip)
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified

def validate_target(url: str, policy: CrawlPolicy, resolver=socket.getaddrinfo) -> tuple[str,...]:
    p=urlparse(url)
    if p.scheme not in policy.schemes or not p.hostname: raise PolicyViolation("unsupported scheme or missing hostname")
    port=p.port or (443 if p.scheme=="https" else 80)
    if port not in policy.allowed_ports: raise PolicyViolation("port is not allowed")
    try:
        addresses=(p.hostname,) if _is_ip(p.hostname) else tuple(dict.fromkeys(info[4][0] for info in resolver(p.hostname,port,type=socket.SOCK_STREAM)))
    except OSError as exc: raise PolicyViolation("DNS resolution failed") from exc
    if not addresses: raise PolicyViolation("DNS returned no addresses")
    if not policy.allow_private and any(_unsafe(a) for a in addresses): raise PolicyViolation("private or reserved destination blocked")
    return addresses

def _is_ip(value: str) -> bool:
    try: ipaddress.ip_address(value); return True
    except ValueError: return False

def validate_redirect_chain(urls: list[str], policy: CrawlPolicy, resolver=socket.getaddrinfo) -> None:
    if len(urls)-1 > policy.max_redirects: raise PolicyViolation("redirect budget exceeded")
    for url in urls: validate_target(url,policy,resolver)
