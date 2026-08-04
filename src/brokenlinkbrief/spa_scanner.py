"""SPA Scanner: JavaScript-rendered link extraction via Playwright.

This module provides SpaScanner which renders pages with a headless browser
to discover links created by client-side JavaScript, then merges them with
raw-HTML link results without duplicates.

Requires the optional ``playwright`` dependency:
    pip install brokenlinkbrief[playwright]
"""
from __future__ import annotations

import contextlib
import html as _html
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from brokenlinkbrief.package import LinkResult

try:
    import playwright  # noqa: F401 — optional dep, checked at runtime

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

_HREF_RE = re.compile(r'href\s*=\s*"([^"]+)"', re.IGNORECASE)


class SpaScanner:
    """Scans a URL for links, optionally rendering JavaScript first.

    When ``render_js=True``, uses Playwright to render the page and discover
    links created by client-side JavaScript (e.g. ``document.createElement('a')``).
    When ``render_js=False``, behaves like the standard regex-based scanner.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_page(self, url: str, render_js: bool = True) -> list[LinkResult]:
        """Scan a single page for links.

        Args:
            url: The target URL to scan.
            render_js: If True, render JavaScript before extracting links.
                       If False, skip Playwright and use raw-HTML extraction only.

        Returns:
            List of LinkResult with status/reason/location per link.
        """
        if not render_js:
            return self._scan_raw(url)

        if not _HAS_PLAYWRIGHT:
            raise NotImplementedError(
                "Playwright is required for JS rendering. "
                "Install it with: pip install brokenlinkbrief[playwright]"
            )

        return self._scan_with_playwright(url)

    def render_and_extract_links(
        self, rendered_html: str, base_url: str
    ) -> list[str]:
        """Extract links from already-rendered HTML content.

        Args:
            rendered_html: The fully rendered HTML string (after JS execution).
            base_url: The base URL for resolving relative links.

        Returns:
            List of absolute URL strings found in the rendered HTML.
        """
        if not rendered_html:
            return []

        seen: set[str] = set()
        urls: list[str] = []
        for match in _HREF_RE.finditer(rendered_html):
            href = match.group(1)
            resolved = urljoin(base_url, _html.unescape(href))
            parsed = urlparse(resolved)
            if parsed.scheme not in ("http", "https"):
                continue
            if resolved not in seen:
                seen.add(resolved)
                urls.append(resolved)
        return urls

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_raw(self, url: str) -> list[LinkResult]:
        """Fetch raw HTML with urllib and extract links (no JS rendering)."""
        req = Request(url, method="GET")
        try:
            with urlopen(req, timeout=10.0) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                charset = "utf-8"
                if "charset=" in content_type:
                    charset = (
                        content_type.split("charset=", 1)[1]
                        .split(";", 1)[0]
                        .strip()
                        or charset
                    )
                data = resp.read()
                body = (
                    data.decode(charset, errors="replace")
                    if isinstance(data, bytes)
                    else str(data)
                )
        except (HTTPError, URLError) as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            return [LinkResult(url=url, status=None, reason=reason, location=None)]

        links = self.render_and_extract_links(body, url)
        return [LinkResult(url=link) for link in links]

    def _scan_with_playwright(self, url: str) -> list[LinkResult]:
        """Use Playwright to render the page and extract JS-generated links."""
        from playwright.sync_api import sync_playwright

        rendered_html = ""
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=self._headless)
                context = browser.new_context()
                page = context.new_page()
                with contextlib.suppress(Exception):
                    page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=30000,
                    )
                rendered_html = page.content()
                browser.close()
        except Exception:
            # Playwright itself failed — return partial results
            return [
                LinkResult(
                    url=url,
                    status=None,
                    reason="playwright-error",
                    location=None,
                )
            ]

        links = self.render_and_extract_links(rendered_html, url)
        return [LinkResult(url=link) for link in links]
