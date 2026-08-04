"""Tests for SPA Scanner module (spa_scanner.py).

Three-layer pre-dev test pattern:
  Layer 1: Import / class existence (PASS immediately)
  Layer 2: Signature / type-hint checks (PASS immediately)
  Layer 3: Behavioral stubs (FAIL with NotImplementedError)
"""
from __future__ import annotations

import inspect
from dataclasses import fields
from typing import get_type_hints

import pytest

from brokenlinkbrief.package import LinkResult
from brokenlinkbrief.spa_scanner import SpaScanner


# ---------------------------------------------------------------------------
# Layer 1 — Import & class existence
# ---------------------------------------------------------------------------
class TestSpaScannerImport:
    """Verify all public symbols are importable."""

    def test_import_spa_scanner(self) -> None:
        assert SpaScanner is not None

    def test_import_link_result(self) -> None:
        assert LinkResult is not None

    def test_spa_scanner_is_class(self) -> None:
        assert inspect.isclass(SpaScanner)

    def test_spa_scanner_instantiable(self) -> None:
        scanner = SpaScanner()
        assert scanner is not None

    def test_spa_scanner_headless_default(self) -> None:
        scanner = SpaScanner()
        assert scanner._headless is True

    def test_spa_scanner_headless_override(self) -> None:
        scanner = SpaScanner(headless=False)
        assert scanner._headless is False


# ---------------------------------------------------------------------------
# Layer 2 — Signature & interface checks
# ---------------------------------------------------------------------------
class TestSpaScannerInterface:
    """Verify method signatures and type hints match the spec."""

    def test_has_scan_page_method(self) -> None:
        assert hasattr(SpaScanner, "scan_page")

    def test_has_render_and_extract_links_method(self) -> None:
        assert hasattr(SpaScanner, "render_and_extract_links")

    def test_scan_page_is_callable(self) -> None:
        assert callable(SpaScanner.scan_page)

    def test_render_and_extract_links_is_callable(self) -> None:
        assert callable(SpaScanner.render_and_extract_links)

    def test_scan_page_signature(self) -> None:
        sig = inspect.signature(SpaScanner.scan_page)
        param_names = list(sig.parameters.keys())
        # self, url, render_js
        assert "url" in param_names
        assert "render_js" in param_names

    def test_scan_page_url_annotation(self) -> None:
        sig = inspect.signature(SpaScanner.scan_page)
        assert sig.parameters["url"].annotation is not inspect.Parameter.empty

    def test_scan_page_render_js_default(self) -> None:
        sig = inspect.signature(SpaScanner.scan_page)
        assert sig.parameters["render_js"].default is True

    def test_scan_page_return_annotation(self) -> None:
        sig = inspect.signature(SpaScanner.scan_page)
        ret = sig.return_annotation
        # with `from __future__ import annotations`, return annotation may be a string
        assert ret is not inspect.Parameter.empty, "scan_page needs return annotation"
        assert ret == "list[LinkResult]" or ret is list[LinkResult]

    def test_render_and_extract_links_signature(self) -> None:
        sig = inspect.signature(SpaScanner.render_and_extract_links)
        param_names = list(sig.parameters.keys())
        assert "rendered_html" in param_names
        assert "base_url" in param_names

    def test_render_and_extract_links_return_annotation(self) -> None:
        sig = inspect.signature(SpaScanner.render_and_extract_links)
        ret = sig.return_annotation
        assert ret is not inspect.Parameter.empty
        assert ret == "list[str]" or ret is list[str]

    def test_scan_page_type_hints_present(self) -> None:
        hints = get_type_hints(SpaScanner.scan_page)
        assert "url" in hints or "return" in hints

    def test_render_and_extract_links_type_hints_present(self) -> None:
        hints = get_type_hints(SpaScanner.render_and_extract_links)
        assert "rendered_html" in hints or "return" in hints


# ---------------------------------------------------------------------------
# Layer 3 — Behavioral stubs (RED phase — fail with NotImplementedError)
# ---------------------------------------------------------------------------
class TestSpaScannerBehavior:
    """Behavioral tests that exercise stub methods.

    Each test MUST raise NotImplementedError until the developer implements
    the real logic. This is the TDD RED phase.
    """

    # --- scan_page behavioral tests ---

    def test_scan_page_js_rendered_links(self) -> None:
        """SPA scan discovers links rendered by JavaScript
        (e.g., links created by document.createElement)."""
        scanner = SpaScanner()
        with pytest.raises(NotImplementedError):
            scanner.scan_page("https://example.com/spa", render_js=True)

    def test_scan_page_no_render_fallback(self) -> None:
        """When render_js=False, no Playwright launch occurs."""
        scanner = SpaScanner()
        # render_js=False should NOT raise — it uses raw urllib, no Playwright
        results = scanner.scan_page(
            "https://example.com/static", render_js=False
        )
        assert isinstance(results, list)

    def test_scan_page_returns_link_result_list(self) -> None:
        """scan_page must return list[LinkResult]."""
        scanner = SpaScanner()
        try:
            results = scanner.scan_page("https://example.com", render_js=False)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(results, list)
        for item in results:
            assert isinstance(item, LinkResult)

    def test_scan_page_deduplicates_spa_and_raw_links(self) -> None:
        """Merges SPA-discovered links with raw-HTML link results without duplicates."""
        scanner = SpaScanner()
        with pytest.raises(NotImplementedError):
            scanner.scan_page("https://example.com/dedup", render_js=True)

    def test_scan_page_fetch_failed_returns_partial(self) -> None:
        """Handles browser timeout gracefully (partial results, no crash)."""
        scanner = SpaScanner()
        try:
            results = scanner.scan_page("https://invalid.example.test", render_js=True)
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        # After implementation: at least one LinkResult with failure reason
        assert isinstance(results, list)

    def test_scan_page_dynamic_tabs_accordions(self) -> None:
        """Extracts links from dynamically opened tabs/accordions."""
        scanner = SpaScanner()
        with pytest.raises(NotImplementedError):
            scanner.scan_page("https://example.com/accordions", render_js=True)

    # --- render_and_extract_links behavioral tests ---

    def test_render_and_extract_links_returns_list(self) -> None:
        """render_and_extract_links must return list[str]."""
        scanner = SpaScanner()
        try:
            links = scanner.render_and_extract_links("<html></html>", "https://example.com")
        except NotImplementedError:
            pytest.skip("Not implemented yet — RED phase")
        assert isinstance(links, list)
        for link in links:
            assert isinstance(link, str)

    def test_render_and_extract_links_resolves_relative(self) -> None:
        """Extracted links are resolved to absolute URLs using base_url."""
        scanner = SpaScanner()
        links = scanner.render_and_extract_links(
            '<a href="/page">link</a>', "https://example.com"
        )
        assert links == ["https://example.com/page"]

    def test_render_and_extract_links_deduplicates(self) -> None:
        """Same URL appearing multiple times yields only one result."""
        scanner = SpaScanner()
        links = scanner.render_and_extract_links(
            '<a href="https://example.com/a"></a>'
            '<a href="https://example.com/a"></a>',
            "https://example.com",
        )
        assert links == ["https://example.com/a"]

    def test_render_and_extract_links_js_created_elements(self) -> None:
        """Links created via document.createElement are present in rendered HTML."""
        scanner = SpaScanner()
        html_with_js_links = (
            '<html><body>'
            '<script>document.body.innerHTML += \'<a href="https://dynamic.example.com">Dynamic</a>\'</script>'
            '</body></html>'
        )
        # render_and_extract_links parses whatever HTML it receives
        links = scanner.render_and_extract_links(
            html_with_js_links, "https://example.com"
        )
        assert "https://dynamic.example.com" in links

    def test_render_and_extract_links_empty_html(self) -> None:
        """Empty HTML yields an empty list."""
        scanner = SpaScanner()
        links = scanner.render_and_extract_links("", "https://example.com")
        assert links == []

    def test_render_and_extract_links_extracts_all_href(self) -> None:
        """All href attributes in the rendered HTML are extracted."""
        scanner = SpaScanner()
        html = (
            '<html><body>'
            '<a href="https://a.example.com">A</a>'
            '<a href="https://b.example.com">B</a>'
            '<a href="https://c.example.com">C</a>'
            '</body></html>'
        )
        links = scanner.render_and_extract_links(html, "https://example.com")
        assert links == [
            "https://a.example.com",
            "https://b.example.com",
            "https://c.example.com",
        ]


# ---------------------------------------------------------------------------
# Layer 3 — LinkResult integration (structural, pass immediately)
# ---------------------------------------------------------------------------
class TestLinkResultStructure:
    """Verify LinkResult dataclass fields used by SpaScanner."""

    def test_link_result_is_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(LinkResult)

    def test_link_result_fields(self) -> None:
        field_names = {f.name for f in fields(LinkResult)}
        expected = {"url", "status", "reason", "location"}
        assert expected == field_names

    def test_link_result_defaults(self) -> None:
        rec = LinkResult(url="https://example.com")
        assert rec.status is None
        assert rec.reason is None
        assert rec.location is None
