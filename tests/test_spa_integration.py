"""Integration tests using a REAL headless Playwright browser against a local
SPA test fixture — NOT MockTransport (TDD Gate v3 real-path requirement).

Tests cover the full pipeline:
  1. SpaScanner discovers JS-rendered links via Playwright
  2. LinkStateStore persists scan snapshots
  3. DiffDetector classifies new/broken/changed between snapshots
  4. DiffAlerter fires notifications for state changes
  5. RegressionDetector detects newly broken links

Uses pytest fixtures for server lifecycle (setup/teardown).
"""

from __future__ import annotations

import http.server
import socket
import sqlite3
import threading
from collections.abc import Generator
from pathlib import Path
from urllib.request import urlopen

import pytest

from brokenlinkbrief.diff_alerts import DiffNotificationTemplates, diff_notify_all
from brokenlinkbrief.diff_detector import DiffDetector
from brokenlinkbrief.link_state import LinkStateStore
from brokenlinkbrief.notifications import NotifierConfig
from brokenlinkbrief.package import LinkResult
from brokenlinkbrief.regression_detector import RegressionDetector
from brokenlinkbrief.spa_scanner import SpaScanner

# ---------------------------------------------------------------------------
# Skip entire module when Playwright is not installed
# ---------------------------------------------------------------------------
try:
    import playwright  # noqa: F401

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

pytestmark = pytest.mark.skipif(
    not _HAS_PLAYWRIGHT,
    reason="Playwright not installed — integration tests require real browser",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _allocate_port() -> int:
    """Allocate an ephemeral port and release it."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _FixtureHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static files from the fixtures directory."""

    def __init__(
        self, *args: object, directory: str | None = None, **kwargs: object
    ) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress request logs during tests."""


@pytest.fixture()
def spa_fixture_server() -> Generator[str, None, None]:
    """Start a local HTTP server serving the fixtures directory.

    Yields the base URL (e.g. ``http://127.0.0.1:PORT``).
    Server is shut down after the test.
    """
    port = _allocate_port()
    handler = lambda *a, **kw: _FixtureHandler(  # noqa: E731
        *a, directory=str(FIXTURES_DIR), **kw
    )
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Verify server is up
    base = f"http://127.0.0.1:{port}"
    with urlopen(f"{base}/spa_state1.html", timeout=5) as resp:
        assert resp.status == 200

    yield base

    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture()
def spa_scanner() -> SpaScanner:
    """Return a scanner only when the Chromium runtime is actually usable."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        pytest.skip(f"Playwright Chromium unavailable: {exc}")
    return SpaScanner(headless=True)


@pytest.fixture()
def link_state_store() -> Generator[LinkStateStore, None, None]:
    """Return a fresh in-memory LinkStateStore."""
    db = sqlite3.connect(":memory:")
    store = LinkStateStore(db)
    yield store
    db.close()


@pytest.fixture()
def diff_detector(link_state_store: LinkStateStore) -> DiffDetector:
    """Return a DiffDetector backed by the link_state_store fixture."""
    return DiffDetector(link_state_store)


@pytest.fixture()
def diff_notifier_config() -> NotifierConfig:
    """Return a NotifierConfig with both channels disabled (no real sends)."""
    return NotifierConfig(
        email_enabled=False,
        slack_enabled=False,
    )


# ---------------------------------------------------------------------------
# Helper: wait for server to be reachable
# ---------------------------------------------------------------------------
def _wait_for_server(url: str, timeout: float = 5.0) -> None:
    """Busy-wait until the server responds or timeout."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"Server at {url} did not become ready within {timeout}s")


# ---------------------------------------------------------------------------
# Test 1: SpaScanner discovers JS-rendered links via real Playwright
# ---------------------------------------------------------------------------
class TestSpaScannerRealBrowser:
    """SpaScanner + Playwright integration against live SPA fixture."""

    def test_discovers_js_generated_links_state1(
        self, spa_fixture_server: str, spa_scanner: SpaScanner
    ) -> None:
        """SPA scan of state1 finds both JS-generated links (A and C)."""
        url = f"{spa_fixture_server}/spa_state1.html"
        results = spa_scanner.scan_page(url, render_js=True)

        assert isinstance(results, list)
        assert len(results) >= 2, (
            f"Expected at least 2 links from JS rendering, got {len(results)}: "
            f"{[r.url for r in results]}"
        )

        found_urls = {r.url for r in results}
        assert "https://link-a.example.com/page" in found_urls, (
            f"Link A not found. Got: {found_urls}"
        )
        assert "https://link-c.example.com/page" in found_urls, (
            f"Link C not found. Got: {found_urls}"
        )

    def test_discovers_js_generated_links_state2(
        self, spa_fixture_server: str, spa_scanner: SpaScanner
    ) -> None:
        """SPA scan of state2 finds JS-generated links (B and C only)."""
        url = f"{spa_fixture_server}/spa_state2.html"
        results = spa_scanner.scan_page(url, render_js=True)

        assert isinstance(results, list)
        assert len(results) >= 2, (
            f"Expected at least 2 links from JS rendering, got {len(results)}: "
            f"{[r.url for r in results]}"
        )

        found_urls = {r.url for r in results}
        assert "https://link-b.example.com/page" in found_urls
        assert "https://link-c.example.com/page" in found_urls
        assert "https://link-a.example.com/page" not in found_urls, (
            "Link A should NOT be present in state2"
        )

    def test_scan_returns_linkresult_instances(
        self, spa_fixture_server: str, spa_scanner: SpaScanner
    ) -> None:
        """Each result is a proper LinkResult dataclass."""
        url = f"{spa_fixture_server}/spa_state1.html"
        results = spa_scanner.scan_page(url, render_js=True)

        for r in results:
            assert isinstance(r, LinkResult)
            assert r.url.startswith("http")

    def test_render_js_false_finds_no_js_links(
        self, spa_fixture_server: str, spa_scanner: SpaScanner
    ) -> None:
        """Without JS rendering, only static HTML links are found (none here)."""
        url = f"{spa_fixture_server}/spa_state1.html"
        results = spa_scanner.scan_page(url, render_js=False)

        # No static <a> tags in the fixture HTML
        assert isinstance(results, list)
        js_link_urls = {
            "https://link-a.example.com/page",
            "https://link-c.example.com/page",
        }
        found = {r.url for r in results}
        assert not (js_link_urls & found), (
            f"JS links found without rendering — expected none. Got: {found}"
        )


# ---------------------------------------------------------------------------
# Test 2: DiffDetector classifies new/broken/changed between snapshots
# ---------------------------------------------------------------------------
class TestDiffDetectorIntegration:
    """DiffDetector classifies link state changes between two real scans."""

    def test_detects_new_link_and_removed_link(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
        link_state_store: LinkStateStore,
        diff_detector: DiffDetector,
    ) -> None:
        """Scan state1, persist, scan state2, diff → new (B) + removed (A)."""
        project_id = "test-project"
        state1_url = f"{spa_fixture_server}/spa_state1.html"
        state2_url = f"{spa_fixture_server}/spa_state2.html"

        # --- Scan 1: state1 has links A, C ---
        scan1_results = spa_scanner.scan_page(state1_url, render_js=True)
        scan1_dicts = [
            {"url": r.url, "status": r.status, "reason": r.reason}
            for r in scan1_results
        ]
        link_state_store.upsert_links(project_id, state1_url, scan1_dicts)

        # --- Scan 2: state2 has links B, C ---
        scan2_results = spa_scanner.scan_page(state2_url, render_js=True)
        scan2_dicts = [
            {"url": r.url, "status": r.status, "reason": r.reason}
            for r in scan2_results
        ]

        # Compare scan2 against stored scan1
        report = diff_detector.compare(project_id, state1_url, scan2_dicts)

        # Verify new link (B) was detected
        new_urls = {e["url"] for e in report.new_links}
        assert "https://link-b.example.com/page" in new_urls, (
            f"Link B should be detected as new. new_links: {report.new_links}"
        )

        # Verify removed link (A) was detected
        removed_urls = {e["url"] for e in report.removed_links}
        assert "https://link-a.example.com/page" in removed_urls, (
            "Link A should be detected as removed. "
            f"removed_links: {report.removed_links}"
        )

        assert report.has_changes is True

    def test_detects_status_change_broken_link(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
        link_state_store: LinkStateStore,
        diff_detector: DiffDetector,
    ) -> None:
        """Link going from healthy (200) to broken (404) → new_broken."""
        project_id = "test-status-change"
        url = f"{spa_fixture_server}/spa_state1.html"

        # Scan 1: link is healthy
        scan1 = spa_scanner.scan_page(url, render_js=True)
        scan1_dicts = [{"url": r.url, "status": 200, "reason": None} for r in scan1]
        link_state_store.upsert_links(project_id, url, scan1_dicts)

        # Scan 2: same links but link A is now broken (404)
        scan2_dicts = [
            {"url": r.url, "status": 404, "reason": "Not Found"}
            if "link-a" in r.url
            else {"url": r.url, "status": r.status, "reason": r.reason}
            for r in scan1
        ]

        report = diff_detector.compare(project_id, url, scan2_dicts)

        broken_urls = {e["url"] for e in report.new_broken}
        assert "https://link-a.example.com/page" in broken_urls, (
            f"Link A should be new_broken. new_broken: {report.new_broken}"
        )
        assert report.has_changes is True


# ---------------------------------------------------------------------------
# Test 3: DiffAlerter fires notifications for state changes
# ---------------------------------------------------------------------------
class TestDiffAlerterIntegration:
    """DiffAlerter integration with real DiffReport."""

    def test_notification_fires_for_new_broken_link(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
        link_state_store: LinkStateStore,
        diff_detector: DiffDetector,
        diff_notifier_config: NotifierConfig,
    ) -> None:
        """diff_notify_all returns notification outcomes for broken link changes."""
        project_id = "test-alerts"
        url = f"{spa_fixture_server}/spa_state1.html"

        # Scan 1: link is healthy
        scan1 = spa_scanner.scan_page(url, render_js=True)
        scan1_dicts = [{"url": r.url, "status": 200, "reason": None} for r in scan1]
        link_state_store.upsert_links(project_id, url, scan1_dicts)

        # Scan 2: link A goes broken
        scan2_dicts = [
            {"url": r.url, "status": 404, "reason": "Not Found"}
            if "link-a" in r.url
            else {"url": r.url, "status": r.status, "reason": r.reason}
            for r in scan1
        ]

        report = diff_detector.compare(project_id, url, scan2_dicts)

        # DiffAlerter should process the report
        outcome = diff_notify_all(diff_notifier_config, report)

        # Both channels should respond (even if disabled — they return "not configured")
        assert "email" in outcome
        assert "slack" in outcome
        assert isinstance(outcome["email"], dict)
        assert isinstance(outcome["slack"], dict)

    def test_no_notification_when_no_changes(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
        link_state_store: LinkStateStore,
        diff_detector: DiffDetector,
        diff_notifier_config: NotifierConfig,
    ) -> None:
        """diff_notify_all short-circuits when report.has_changes is False."""
        from brokenlinkbrief.diff_detector import DiffReport

        no_change_report = DiffReport(
            project_id="test-no-change",
            target_url=f"{spa_fixture_server}/spa_state1.html",
            timestamp="2025-01-01T00:00:00Z",
            has_changes=False,
        )

        outcome = diff_notify_all(diff_notifier_config, no_change_report)

        # Both channels should indicate no changes
        assert outcome["email"]["sent"] is False
        assert outcome["slack"]["sent"] is False
        assert "no changes" in outcome["email"].get("error", "")

    def test_diff_alert_template_renders_broken_links(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
        link_state_store: LinkStateStore,
        diff_detector: DiffDetector,
    ) -> None:
        """DiffNotificationTemplates.render_diff_alert produces readable output."""
        project_id = "test-template"
        url = f"{spa_fixture_server}/spa_state1.html"

        scan1 = spa_scanner.scan_page(url, render_js=True)
        scan1_dicts = [{"url": r.url, "status": 200, "reason": None} for r in scan1]
        link_state_store.upsert_links(project_id, url, scan1_dicts)

        scan2_dicts = [
            {"url": r.url, "status": 404, "reason": "Not Found"}
            if "link-a" in r.url
            else {"url": r.url, "status": r.status, "reason": r.reason}
            for r in scan1
        ]

        report = diff_detector.compare(project_id, url, scan2_dicts)
        alert_text = DiffNotificationTemplates.render_diff_alert(report)

        assert "Link Diff Alert" in alert_text
        assert "NEW BROKEN LINKS" in alert_text
        assert "link-a.example.com" in alert_text


# ---------------------------------------------------------------------------
# Test 4: RegressionDetector detects newly broken links
# ---------------------------------------------------------------------------
class TestRegressionDetectorIntegration:
    """RegressionDetector integration with real scan data."""

    def test_detects_regression_for_newly_broken_link(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
    ) -> None:
        """RegressionDetector flags link A going from healthy to broken."""
        detector = RegressionDetector()
        url = f"{spa_fixture_server}/spa_state1.html"

        # Scan 1: all healthy
        scan1 = spa_scanner.scan_page(url, render_js=True)
        scan1_dicts = [{"url": r.url, "status": 200, "reason": None} for r in scan1]

        # Scan 2: link A broken
        scan2_dicts = [
            {"url": r.url, "status": 404, "reason": "Not Found"}
            if "link-a" in r.url
            else {"url": r.url, "status": r.status, "reason": r.reason}
            for r in scan1
        ]

        # Build scan history: previous completed scan
        scan_history = [
            {
                "scan_id": "scan-001",
                "status": "completed",
                "scan_timestamp": "2025-01-01T00:00:00Z",
                "raw_results": {url: scan1_dicts},
            }
        ]

        report = detector.detect(
            project_id="test-regression",
            current_results={url: scan2_dicts},
            scan_history=scan_history,
        )

        assert report.has_regressions is True
        assert len(report.new_broken) >= 1

        broken_urls = {e["url"] for e in report.new_broken}
        assert "https://link-a.example.com/page" in broken_urls

    def test_no_regression_when_links_unchanged(
        self,
        spa_fixture_server: str,
        spa_scanner: SpaScanner,
    ) -> None:
        """RegressionDetector reports no regressions when scan is identical."""
        detector = RegressionDetector()
        url = f"{spa_fixture_server}/spa_state1.html"

        scan = spa_scanner.scan_page(url, render_js=True)
        scan_dicts = [{"url": r.url, "status": 200, "reason": None} for r in scan]

        scan_history = [
            {
                "scan_id": "scan-001",
                "status": "completed",
                "scan_timestamp": "2025-01-01T00:00:00Z",
                "raw_results": {url: scan_dicts},
            }
        ]

        report = detector.detect(
            project_id="test-no-regression",
            current_results={url: scan_dicts},
            scan_history=scan_history,
        )

        assert report.has_regressions is False
        assert len(report.new_broken) == 0
        assert len(report.resolved) == 0
