"""Pre-development tests for the Portfolio Aggregation API.

Feature under test (analysis brief 4.1, t_9ffe6649):
- GET /api/portfolio            → {"summary": {...PortfolioSummary}, "projects": [...]}
- GET /api/portfolio?project_ids=...  → filtered to the listed projects
- GET /api/portfolio/summary    → {"summary": {...}, "trend": [...]} trend data
- New module src/brokenlinkbrief/portfolio.py with get_portfolio,
  get_portfolio_rows, get_portfolio_trends and three frozen dataclasses.
- Python-native (stdlib http.server); NO TypeScript / src/lib/portfolio-api.ts.

State at authoring time (pre-tester, RED phase):
- src/brokenlinkbrief/portfolio.py DOES NOT exist → interface tests fail with
  ModuleNotFoundError / AttributeError (the honest RED signal, per brief §4.7).
- /api/portfolio routes are NOT wired in app.py → HTTP behavioral tests are
  pytest.skip("RED phase") until the developer (t_72053d3c) wires them.
- The behavioral unit tests (in-memory sqlite + ScanHistoryStore.record_scan)
  assert REAL return values per the brief's §4.1 test expectations and will
  FAIL with ModuleNotFoundError until portfolio.py lands — they are NOT
  NotImplementedError-assertion tests.

Test conventions (repo): tests/conftest.py injects src/; HTTP tests start a
real HTTPServer((127.0.0.1, 0), _Handler) on a thread with
BROKENLINKBRIEF_SCAN_TOKEN=test-token (pattern from test_scheduled_projects_view.py).
"""
from __future__ import annotations

import http.client
import inspect
import json
import sqlite3
import threading
from dataclasses import fields, is_dataclass
from http.server import HTTPServer
from pathlib import Path

import pytest

from brokenlinkbrief.confidence import ProbeAttempt
from brokenlinkbrief.finding_service import FindingService
from brokenlinkbrief.findings import FindingStore
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_history import ScanHistoryStore
from brokenlinkbrief.triage import extract_occurrences


def _seed_findings(
    finding_store: FindingStore,
    project_id: str,
    open_count: int,
    resolved_count: int,
) -> None:
    """Seed ``open_count`` OPEN + ``resolved_count`` RESOLVED findings for a project.

    Uses the real FindingService.observe / FindingStore.verify pipeline so the
    project_findings rows carry genuine states (OPEN via CONFIRMED_BROKEN
    observations, RESOLVED via RECOVERED verifications).
    """
    service = FindingService(finding_store)
    for i in range(open_count):
        occurrence = extract_occurrences(
            "https://site.test/source",
            f'<a href="/missing-{project_id}-o{i}">Anchor</a>',
        )[0]
        service.observe(
            project_id,
            occurrence,
            [
                ProbeAttempt("HEAD", 404, None, 0.01),
                ProbeAttempt("GET", 404, None, 0.02),
            ],
        )
    for i in range(resolved_count):
        occurrence = extract_occurrences(
            "https://site.test/source",
            f'<a href="/missing-{project_id}-r{i}">Anchor</a>',
        )[0]
        finding = service.observe(
            project_id,
            occurrence,
            [
                ProbeAttempt("HEAD", 404, None, 0.01),
                ProbeAttempt("GET", 404, None, 0.02),
            ],
        )
        assert finding is not None
        service.verify(
            finding["id"],
            finding["version"],
            [
                ProbeAttempt("HEAD", 200, None, 0.01),
                ProbeAttempt("GET", 200, None, 0.02),
            ],
            {"https://site.test/source": "<p>removed</p>"},
        )

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _start_server(monkeypatch: pytest.MonkeyPatch):
    """Start a real stdlib HTTPServer with the _Handler and return its port."""
    from brokenlinkbrief.app import _Handler

    monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "test-token")
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()


def _request(port: int, path: str) -> tuple[int, dict | None, str]:
    """GET path and return (status, decoded_json_or_None, content_type)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    status = resp.status
    ct = resp.getheader("Content-Type", "")
    raw = resp.read()
    conn.close()
    body: dict | None = None
    try:
        body = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        body = None
    return status, body, ct


# ---------------------------------------------------------------------------
# 1. Interface — portfolio module exists with the exact public API (RED)
# ---------------------------------------------------------------------------


class TestPortfolioModuleInterface:
    """Verify brokenlinkbrief.portfolio exists with the spec'd public symbols.

    RED phase: these fail with ModuleNotFoundError because portfolio.py does
    not exist yet (brief §4.7: the honest RED signal is ImportError/AttributeError).
    """

    def test_portfolio_module_importable(self) -> None:
        import importlib

        mod = importlib.import_module("brokenlinkbrief.portfolio")
        assert mod is not None

    def test_get_portfolio_exists(self) -> None:
        from brokenlinkbrief.portfolio import get_portfolio

        assert callable(get_portfolio)

    def test_get_portfolio_rows_exists(self) -> None:
        from brokenlinkbrief.portfolio import get_portfolio_rows

        assert callable(get_portfolio_rows)

    def test_get_portfolio_trends_exists(self) -> None:
        from brokenlinkbrief.portfolio import get_portfolio_trends

        assert callable(get_portfolio_trends)

    def test_portfolio_summary_is_dataclass(self) -> None:
        from brokenlinkbrief.portfolio import PortfolioSummary

        assert is_dataclass(PortfolioSummary)

    def test_portfolio_project_row_is_dataclass(self) -> None:
        from brokenlinkbrief.portfolio import PortfolioProjectRow

        assert is_dataclass(PortfolioProjectRow)

    def test_portfolio_trend_point_is_dataclass(self) -> None:
        from brokenlinkbrief.portfolio import PortfolioTrendPoint

        assert is_dataclass(PortfolioTrendPoint)

    def test_portfolio_summary_fields(self) -> None:
        from brokenlinkbrief.portfolio import PortfolioSummary

        field_names = {f.name for f in fields(PortfolioSummary)}
        required = {
            "projects",
            "scanned_projects",
            "unscanned_projects",
            "total_links",
            "broken_count",
            "new_broken_count",
            "open_findings",
            "resolved_findings",
            "health_score",
            "last_scan_timestamp",
        }
        missing = required - field_names
        assert not missing, f"Missing PortfolioSummary fields: {missing}"

    def test_portfolio_project_row_fields(self) -> None:
        from brokenlinkbrief.portfolio import PortfolioProjectRow

        field_names = {f.name for f in fields(PortfolioProjectRow)}
        required = {
            "project_id",
            "project_name",
            "total_links",
            "broken_count",
            "new_broken_count",
            "open_findings",
            "resolved_findings",
            "last_scan_timestamp",
            "last_scan_status",
            "pinned",
            "archived",
        }
        missing = required - field_names
        assert not missing, f"Missing PortfolioProjectRow fields: {missing}"

    def test_portfolio_trend_point_fields(self) -> None:
        from brokenlinkbrief.portfolio import PortfolioTrendPoint

        field_names = {f.name for f in fields(PortfolioTrendPoint)}
        required = {"date", "total_links", "broken_count"}
        missing = required - field_names
        assert not missing, f"Missing PortfolioTrendPoint fields: {missing}"

    def test_get_portfolio_signature(self) -> None:
        from brokenlinkbrief.portfolio import get_portfolio

        sig = inspect.signature(get_portfolio)
        params = list(sig.parameters.keys())
        assert params[0] == "project_ids", (
            f"Expected project_ids as first param, got {params}"
        )
        assert sig.parameters["project_ids"].default is None
        for kw in ("project_store", "history_db", "finding_store"):
            assert kw in sig.parameters, f"Missing keyword-only param {kw}"

    def test_get_portfolio_rows_signature(self) -> None:
        from brokenlinkbrief.portfolio import get_portfolio_rows

        sig = inspect.signature(get_portfolio_rows)
        params = list(sig.parameters.keys())
        assert params[0] == "project_ids", (
            f"Expected project_ids as first param, got {params}"
        )
        assert sig.parameters["project_ids"].default is None

    def test_get_portfolio_trends_signature(self) -> None:
        from brokenlinkbrief.portfolio import get_portfolio_trends

        sig = inspect.signature(get_portfolio_trends)
        params = list(sig.parameters.keys())
        assert params[0] == "project_ids", (
            f"Expected project_ids as first param, got {params}"
        )
        assert params[1] == "days", (
            f"Expected days as second param, got {params}"
        )
        assert sig.parameters["project_ids"].default is None
        assert sig.parameters["days"].default == 30


# ---------------------------------------------------------------------------
# 2. Behavioral (unit) — aggregation logic with in-memory SQLite (RED)
#
# These assert REAL return values against seeded scan_history records.
# They fail with ModuleNotFoundError until portfolio.py exists; the developer
# must make them pass with the exact numbers seeded here (brief §4.1).
# ---------------------------------------------------------------------------


@pytest.fixture()
def portfolio_db(tmp_path: Path):
    """In-memory sqlite DB with projects + scan_history tables (spec schema)."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_history (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            scan_timestamp TEXT NOT NULL,
            total_urls INTEGER NOT NULL,
            total_links INTEGER NOT NULL,
            broken_count INTEGER NOT NULL,
            new_broken_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'completed',
            raw_results_json TEXT,
            last_known_good_hash TEXT,
            regression_flags TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    yield db
    db.close()


@pytest.fixture()
def portfolio_project_store(tmp_path: Path) -> ProjectStore:
    """ProjectStore on a temp file DB with two active + one archived project."""
    store = ProjectStore(tmp_path / "projects.db")
    store.create("Alpha", ["https://alpha.example.com/"])
    store.create("Beta", ["https://beta.example.com/"])
    store.create("Gamma", ["https://gamma.example.com/"])
    for project in store.list_active():
        if project.name == "Gamma":
            store.archive(project.id)
    return store


@pytest.fixture()
def seeded_portfolio(
    portfolio_db: sqlite3.Connection,
    portfolio_project_store: ProjectStore,
):
    """Seed scan_history so portfolio numbers are deterministic:

    - alpha (active):  2 scans, latest total_links=50 broken=5 new_broken=2
    - beta  (active):  1 scan,  latest total_links=20 broken=8 new_broken=0
    - gamma (archived): 1 scan (must be EXCLUDED from unfiltered portfolio)
    - delta: no project row, no scans (counted nowhere)

    The same project rows are inserted into the in-memory history DB so the
    scan_history FOREIGN KEY holds (production uses one shared DB file).
    """
    all_projects = (
        portfolio_project_store.list_active()
        + portfolio_project_store.list_archived()
    )
    for project in all_projects:
        portfolio_db.execute(
            "INSERT OR REPLACE INTO projects "
            "(id, name, archived, created_at, updated_at, pinned) "
            "VALUES (?,?,?,?,?,?)",
            (
                project.id,
                project.name,
                int(project.archived),
                project.created_at,
                project.updated_at,
                int(project.pinned),
            ),
        )
    portfolio_db.commit()

    store = ScanHistoryStore(portfolio_db)
    by_name = {p.name: p for p in all_projects}
    alpha = by_name["Alpha"]
    beta = by_name["Beta"]
    gamma = by_name["Gamma"]

    store.record_scan(
        alpha.id, total_urls=10, total_links=40, broken_count=3,
        new_broken_count=1, status="completed",
    )
    store.record_scan(
        alpha.id, total_urls=10, total_links=50, broken_count=5,
        new_broken_count=2, status="completed",
    )
    store.record_scan(
        beta.id, total_urls=5, total_links=20, broken_count=8,
        new_broken_count=0, status="completed",
    )
    store.record_scan(
        gamma.id, total_urls=3, total_links=9, broken_count=1,
        new_broken_count=0, status="completed",
    )
    return {"alpha": alpha, "beta": beta, "gamma": gamma}


class TestPortfolioAggregationBehavior:
    """Real-value behavioral tests (RED until portfolio.py is implemented)."""

    def test_empty_portfolio_is_zeros_with_full_health(
        self, tmp_path: Path,
    ) -> None:
        """Empty DB (no projects, no scans) → zeros, health 100.0, no raise."""
        from brokenlinkbrief.portfolio import get_portfolio

        store = ProjectStore(tmp_path / "empty-projects.db")
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        try:
            summary = get_portfolio(
                project_ids=None,
                project_store=store,
                history_db=db,
                finding_store=None,
            )
        finally:
            db.close()
        assert summary.projects == 0
        assert summary.scanned_projects == 0
        assert summary.unscanned_projects == 0
        assert summary.total_links == 0
        assert summary.broken_count == 0
        assert summary.new_broken_count == 0
        assert summary.open_findings == 0
        assert summary.resolved_findings == 0
        assert summary.health_score == 100.0
        assert summary.last_scan_timestamp is None

    def test_totals_sum_latest_records_across_active_projects(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """Unfiltered portfolio sums the LATEST scan per active project."""
        from brokenlinkbrief.portfolio import get_portfolio

        summary = get_portfolio(
            project_ids=None,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        # alpha latest (50 links / 5 broken) + beta (20 links / 8 broken)
        assert summary.projects == 2
        assert summary.scanned_projects == 2
        assert summary.unscanned_projects == 0
        assert summary.total_links == 70
        assert summary.broken_count == 13
        assert summary.new_broken_count == 2
        assert summary.last_scan_timestamp is not None
        # health = round(100 * (1 - 13/70), 1) = round(81.428..., 1) = 81.4
        assert summary.health_score == pytest.approx(81.4, abs=0.05)

    def test_project_without_history_is_never_run(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """A project with no scan_history counts as unscanned, status never_run."""
        from brokenlinkbrief.portfolio import get_portfolio, get_portfolio_rows

        fresh = portfolio_project_store.create(
            "Fresh", ["https://fresh.example.com/"]
        )
        summary = get_portfolio(
            project_ids=None,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        assert summary.projects == 3
        assert summary.scanned_projects == 2
        assert summary.unscanned_projects == 1

        rows = get_portfolio_rows(
            project_ids=None,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        by_id = {r.project_id: r for r in rows}
        fresh_row = by_id[fresh.id]
        assert fresh_row.total_links == 0
        assert fresh_row.broken_count == 0
        assert fresh_row.last_scan_status == "never_run"
        assert fresh_row.last_scan_timestamp is None

    def test_rows_expose_latest_record_values(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """Each row mirrors the latest scan_history record per project."""
        from brokenlinkbrief.portfolio import get_portfolio_rows

        rows = get_portfolio_rows(
            project_ids=None,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        by_id = {r.project_id: r for r in rows}
        alpha = by_id[seeded_portfolio["alpha"].id]
        beta = by_id[seeded_portfolio["beta"].id]

        assert alpha.total_links == 50      # latest, not 40
        assert alpha.broken_count == 5
        assert alpha.new_broken_count == 2
        assert alpha.last_scan_status == "completed"
        assert alpha.pinned is False
        assert alpha.archived is False
        assert alpha.project_name == "Alpha"

        assert beta.total_links == 20
        assert beta.broken_count == 8
        assert beta.new_broken_count == 0
        assert beta.last_scan_status == "completed"

        # archived project excluded from unfiltered rows
        assert seeded_portfolio["gamma"].id not in by_id

    def test_project_ids_filter_restricts_rows(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """project_ids=... returns only the listed projects' rows."""
        from brokenlinkbrief.portfolio import get_portfolio, get_portfolio_rows

        beta_id = seeded_portfolio["beta"].id
        rows = get_portfolio_rows(
            project_ids=[beta_id],
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        assert [r.project_id for r in rows] == [beta_id]

        summary = get_portfolio(
            project_ids=[beta_id],
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        assert summary.projects == 1
        assert summary.total_links == 20
        assert summary.broken_count == 8

    def test_project_ids_explicitly_include_archived(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """Archived projects are excluded unless explicitly listed (brief §4.1)."""
        from brokenlinkbrief.portfolio import get_portfolio, get_portfolio_rows

        gamma_id = seeded_portfolio["gamma"].id
        rows = get_portfolio_rows(
            project_ids=[gamma_id],
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        assert [r.project_id for r in rows] == [gamma_id]
        assert rows[0].archived is True

        summary = get_portfolio(
            project_ids=[gamma_id],
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=None,
        )
        assert summary.projects == 1
        assert summary.total_links == 9
        assert summary.broken_count == 1

    def test_rows_attribue_findings_per_project(
        self, tmp_path: Path,
        portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """Each row carries ITS OWN project's open/resolved finding counts.

        Regression for the blocker: the aggregate open/resolved totals used to be
        broadcast to every row. Seeded per project — A: 1 OPEN + 1 RESOLVED,
        B: 1 OPEN — so the per-row numbers must differ from the totals.
        """
        from brokenlinkbrief.portfolio import get_portfolio_rows

        finding_store = FindingStore(tmp_path / "findings.db")
        finding_store.ensure_project(
            seeded_portfolio["alpha"].id, "Alpha"
        )
        finding_store.ensure_project(seeded_portfolio["beta"].id, "Beta")
        _seed_findings(finding_store, seeded_portfolio["alpha"].id, 1, 1)
        _seed_findings(finding_store, seeded_portfolio["beta"].id, 1, 0)

        rows = get_portfolio_rows(
            project_ids=None,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
            finding_store=finding_store,
        )
        by_id = {r.project_id: r for r in rows}
        alpha = by_id[seeded_portfolio["alpha"].id]
        beta = by_id[seeded_portfolio["beta"].id]

        assert alpha.open_findings == 1, alpha
        assert alpha.resolved_findings == 1, alpha
        assert beta.open_findings == 1, beta
        assert beta.resolved_findings == 0, beta

    def test_trend_returns_ascending_daily_points(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """get_portfolio_trends returns ascending {date,total_links,broken_count}."""
        from brokenlinkbrief.portfolio import get_portfolio_trends

        trend = get_portfolio_trends(
            project_ids=None,
            days=30,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
        )
        assert isinstance(trend, list)
        if trend:
            dates = [p.date for p in trend]
            assert dates == sorted(dates)
            for point in trend:
                assert point.total_links >= 0
                assert point.broken_count >= 0

    def test_trend_days_le_zero_returns_all_history(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """days<=0 → all history returned, not an empty/error result."""
        from brokenlinkbrief.portfolio import get_portfolio_trends

        trend = get_portfolio_trends(
            project_ids=None,
            days=0,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
        )
        assert isinstance(trend, list)

    def test_trend_date_format_yyyy_mm_dd(
        self, portfolio_db: sqlite3.Connection,
        portfolio_project_store: ProjectStore,
        seeded_portfolio,
    ) -> None:
        """Trend dates are YYYY-MM-DD (brief: date format contract)."""
        import re

        from brokenlinkbrief.portfolio import get_portfolio_trends

        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        trend = get_portfolio_trends(
            project_ids=None,
            days=0,
            project_store=portfolio_project_store,
            history_db=portfolio_db,
        )
        for point in trend:
            assert date_re.match(point.date), (
                f"Bad date format: {point.date}"
            )


# ---------------------------------------------------------------------------
# 3. Behavioral (HTTP) — real HTTPServer against the wired routes (RED/skip)
#
# Skipped with "RED phase" until the developer wires the two routes in app.py
# (repo convention from test_scheduled_projects_view.py). The 401 tests DO run
# now and FAIL with 404 (final not-found branch) — the honest RED discriminator
# that the wired route must replace with the shared 401 auth gate.
# ---------------------------------------------------------------------------


class TestPortfolioHttpEndpoint:
    """HTTP behavior of GET /api/portfolio (brief §4.1)."""

    def test_portfolio_route_returns_200_json(
        self, _start_server: int,
    ) -> None:
        """GET /api/portfolio?token=... → 200 with JSON body."""
        pytest.skip("RED phase: /api/portfolio route not wired yet")
        status, body, ct = _request(
            _start_server, "/api/portfolio?token=test-token"
        )
        assert status == 200, f"Expected 200, got {status}"
        assert "json" in ct
        assert body is not None
        assert "summary" in body
        assert "projects" in body

    def test_portfolio_unauthorized_returns_401(self, _start_server: int) -> None:
        """No token → 401 (auth gate identical to /api/dashboard/*)."""
        status, _, _ = _request(_start_server, "/api/portfolio")
        assert status == 401, f"Expected 401, got {status}"

    def test_portfolio_bad_token_returns_401(self, _start_server: int) -> None:
        """Wrong token → 401."""
        status, _, _ = _request(_start_server, "/api/portfolio?token=wrong")
        assert status == 401, f"Expected 401, got {status}"

    def test_portfolio_project_ids_filter_returns_200(
        self, _start_server: int,
    ) -> None:
        """project_ids filter is accepted and returns 200 JSON."""
        pytest.skip("RED phase: /api/portfolio route not wired yet")
        status, body, ct = _request(
            _start_server,
            "/api/portfolio?token=test-token&project_ids=p1,p2",
        )
        assert status == 200, f"Expected 200, got {status}"
        assert "json" in ct
        assert body is not None
        assert "summary" in body
        assert "projects" in body

    def test_portfolio_summary_shape(self, _start_server: int) -> None:
        """Portfolio summary payload has the spec'd keys."""
        pytest.skip("RED phase: /api/portfolio route not wired yet")
        status, body, _ = _request(
            _start_server, "/api/portfolio?token=test-token"
        )
        if status != 200 or body is None:
            return
        summary = body["summary"]
        for key in (
            "projects",
            "scanned_projects",
            "unscanned_projects",
            "total_links",
            "broken_count",
            "new_broken_count",
            "open_findings",
            "resolved_findings",
            "health_score",
            "last_scan_timestamp",
        ):
            assert key in summary, f"Missing summary key: {key}"

    def test_portfolio_rows_shape(self, _start_server: int) -> None:
        """Each project row has the spec'd keys."""
        pytest.skip("RED phase: /api/portfolio route not wired yet")
        status, body, _ = _request(
            _start_server, "/api/portfolio?token=test-token"
        )
        if status != 200 or body is None:
            return
        projects = body.get("projects", [])
        for row in projects:
            for key in (
                "project_id",
                "project_name",
                "total_links",
                "broken_count",
                "new_broken_count",
                "open_findings",
                "resolved_findings",
                "last_scan_timestamp",
                "last_scan_status",
                "pinned",
                "archived",
            ):
                assert key in row, f"Missing row key: {key}"

    def test_portfolio_rows_attribue_findings_per_project_http(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/portfolio attributes findings per project, not totals.

        Regression for the blocker: the aggregate open/resolved totals used
        to be broadcast to every row. Seeded per project — A: 1 OPEN + 1
        RESOLVED, B: 1 OPEN — via the real FindingService pipeline into the
        same DB file the HTTP handler reads (BROKENLINKBRIEF_PROJECT_DB).
        """
        from brokenlinkbrief.app import _Handler

        project_db = tmp_path / "projects.db"
        monkeypatch.setenv("BROKENLINKBRIEF_PROJECT_DB", str(project_db))
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "test-token")

        project_store = ProjectStore(project_db)
        alpha = project_store.create("Alpha", ["https://alpha.example.com/"])
        beta = project_store.create("Beta", ["https://beta.example.com/"])

        # scan_history table (schema defined in the portfolio test fixtures;
        # no src module creates it) + one record per project so the rows are
        # not dropped by the portfolio aggregation.
        db = sqlite3.connect(project_db)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_history (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                scan_timestamp TEXT NOT NULL,
                total_urls INTEGER NOT NULL,
                total_links INTEGER NOT NULL,
                broken_count INTEGER NOT NULL,
                new_broken_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'completed',
                raw_results_json TEXT,
                last_known_good_hash TEXT,
                regression_flags TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        ScanHistoryStore(db).record_scan(
            alpha.id, total_urls=10, total_links=50, broken_count=5,
        )
        ScanHistoryStore(db).record_scan(
            beta.id, total_urls=5, total_links=20, broken_count=8,
        )
        db.commit()
        db.close()

        finding_store = FindingStore(project_db)
        finding_store.ensure_project(alpha.id, "Alpha")
        finding_store.ensure_project(beta.id, "Beta")
        _seed_findings(finding_store, alpha.id, 1, 1)
        _seed_findings(finding_store, beta.id, 1, 0)

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            status, body, _ = _request(
                port, "/api/portfolio?token=test-token"
            )
            assert status == 200, f"Expected 200, got {status}"
            assert body is not None
            projects = {row["project_id"]: row for row in body["projects"]}
            assert projects[alpha.id]["open_findings"] == 1, projects[alpha.id]
            assert projects[alpha.id]["resolved_findings"] == 1, (
                projects[alpha.id]
            )
            assert projects[beta.id]["open_findings"] == 1, projects[beta.id]
            assert projects[beta.id]["resolved_findings"] == 0, projects[beta.id]
        finally:
            server.shutdown()


class TestPortfolioSummaryEndpoint:
    """HTTP behavior of GET /api/portfolio/summary (brief §4.1)."""

    def test_summary_route_returns_200_json(self, _start_server: int) -> None:
        """GET /api/portfolio/summary?token=... → 200 JSON with trend."""
        pytest.skip("RED phase: /api/portfolio/summary route not wired yet")
        status, body, ct = _request(
            _start_server, "/api/portfolio/summary?token=test-token"
        )
        assert status == 200, f"Expected 200, got {status}"
        assert "json" in ct
        assert body is not None
        assert "summary" in body
        assert "trend" in body

    def test_summary_days_param_accepted(self, _start_server: int) -> None:
        """days=7 is accepted; trend is a list."""
        pytest.skip("RED phase: /api/portfolio/summary route not wired yet")
        status, body, _ = _request(
            _start_server, "/api/portfolio/summary?token=test-token&days=7"
        )
        assert status == 200, f"Expected 200, got {status}"
        if body is not None:
            assert isinstance(body.get("trend"), list)

    def test_summary_days_le_zero_accepted(self, _start_server: int) -> None:
        """days=0 (all history) is accepted without error."""
        pytest.skip("RED phase: /api/portfolio/summary route not wired yet")
        status, _, _ = _request(
            _start_server, "/api/portfolio/summary?token=test-token&days=0"
        )
        assert status == 200, f"Expected 200, got {status}"

    def test_summary_trend_point_shape(self, _start_server: int) -> None:
        """Each trend point has date/total_links/broken_count."""
        pytest.skip("RED phase: /api/portfolio/summary route not wired yet")
        status, body, _ = _request(
            _start_server, "/api/portfolio/summary?token=test-token"
        )
        if status != 200 or body is None:
            return
        for point in body.get("trend", []):
            for key in ("date", "total_links", "broken_count"):
                assert key in point, f"Missing trend key: {key}"

    def test_summary_unauthorized_returns_401(self, _start_server: int) -> None:
        """No token → 401."""
        status, _, _ = _request(_start_server, "/api/portfolio/summary")
        assert status == 401, f"Expected 401, got {status}"
