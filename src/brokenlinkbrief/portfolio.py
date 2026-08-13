"""Portfolio-level aggregation for the multi-site dashboard.

Aggregates the latest per-project ``scan_history`` records (SQLite) into a
cross-project health overview served by ``GET /api/portfolio`` and
``GET /api/portfolio/summary``. Numbers reconcile to the per-project scan
records produced by :class:`brokenlinkbrief.scan_history.ScanHistoryStore`;
projects with no scan history yet are counted as unscanned (``never_run``).
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brokenlinkbrief.findings import FindingStore
    from brokenlinkbrief.projects import Project, ProjectStore


@dataclass(frozen=True)
class PortfolioProjectRow:
    """One project's aggregated row in the portfolio view."""

    project_id: str
    project_name: str
    total_links: int
    broken_count: int
    new_broken_count: int
    open_findings: int
    resolved_findings: int
    last_scan_timestamp: str | None
    last_scan_status: str  # "completed" | "failed" | "never_run"
    pinned: bool
    archived: bool


@dataclass(frozen=True)
class PortfolioSummary:
    """Cross-project totals."""

    projects: int  # active projects counted
    scanned_projects: int
    unscanned_projects: int
    total_links: int
    broken_count: int
    new_broken_count: int
    open_findings: int
    resolved_findings: int
    health_score: float  # 0.0-100.0, see formula below
    last_scan_timestamp: str | None


@dataclass(frozen=True)
class PortfolioTrendPoint:
    """One day of aggregated broken-link trend across selected projects."""

    date: str  # "YYYY-MM-DD"
    total_links: int
    broken_count: int


def _default_project_store() -> ProjectStore:
    from brokenlinkbrief.projects import ProjectStore

    return ProjectStore()


def _connect_history_db(project_store: ProjectStore) -> sqlite3.Connection:
    """Open a read-only-per-call connection to the shared project DB."""
    db = sqlite3.connect(project_store.path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _default_finding_store() -> FindingStore:
    from brokenlinkbrief.findings import FindingStore

    return FindingStore()


def _resolve_projects(
    project_ids: list[str] | None,
    project_store: ProjectStore,
) -> list[Project]:
    """Return the projects the portfolio should cover.

    ``project_ids=None`` → all active projects.  Archived projects are
    excluded unless explicitly listed in ``project_ids``.
    """
    if project_ids is not None:
        wanted = set(project_ids)
        return [p for p in project_store.list_active() if p.id in wanted] + [
            p for p in project_store.list_archived() if p.id in wanted
        ]
    return project_store.list_active()


def _finding_counts(
    db: sqlite3.Connection,
    project_ids: list[str],
) -> tuple[int, int]:
    """Return (open_findings, resolved_findings) for the given projects.

    Tolerates a DB without the findings tables (``FindingStore`` migration
    not yet applied) by returning zeros.
    """
    if not project_ids:
        return 0, 0
    placeholders = ", ".join("?" for _ in project_ids)
    try:
        rows = db.execute(
            "SELECT state, COUNT(*) AS n FROM project_findings "
            f"WHERE project_id IN ({placeholders}) GROUP BY state",
            project_ids,
        ).fetchall()
    except sqlite3.OperationalError:
        return 0, 0
    open_findings = 0
    resolved_findings = 0
    for row in rows:
        if row["state"] == "OPEN":
            open_findings += row["n"]
        elif row["state"] == "RESOLVED":
            resolved_findings += row["n"]
    return open_findings, resolved_findings


def _per_project_finding_counts(
    db: sqlite3.Connection,
    project_ids: list[str],
) -> dict[str, tuple[int, int]]:
    """Per-project (open, resolved) finding counts in ONE indexed query.

    ``GROUP BY project_id, state`` over the full list — the index on
    (project_id, state, last_seen_at) serves it directly (no N+1).  Projects
    without findings are absent from the result (callers default to 0, 0).
    Tolerates a DB without the findings tables by returning an empty dict.
    """
    if not project_ids:
        return {}
    placeholders = ", ".join("?" for _ in project_ids)
    try:
        rows = db.execute(
            "SELECT project_id, state, COUNT(*) AS n FROM project_findings "
            f"WHERE project_id IN ({placeholders}) GROUP BY project_id, state",
            project_ids,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    counts: dict[str, tuple[int, int]] = {}
    for row in rows:
        open_findings, resolved_findings = counts.get(row["project_id"], (0, 0))
        if row["state"] == "OPEN":
            open_findings += row["n"]
        elif row["state"] == "RESOLVED":
            resolved_findings += row["n"]
        counts[row["project_id"]] = (open_findings, resolved_findings)
    return counts


def _finding_counts_for(
    finding_store: FindingStore | None,
    history_db: sqlite3.Connection,
    project_ids: list[str],
) -> dict[str, tuple[int, int]]:
    """Per-project (open, resolved) counts, honoring the finding store.

    When ``finding_store`` is given, its own DB is queried (the store may
    live in a different file than the scan history DB — e.g. isolated
    tests); the scan ``history_db`` is the fallback (same file in
    production).  Absent table → empty dict → zeros for every project.
    """
    if finding_store is not None:
        try:
            store_db = sqlite3.connect(finding_store.path, timeout=10)
            store_db.row_factory = sqlite3.Row
            try:
                return _per_project_finding_counts(store_db, project_ids)
            finally:
                store_db.close()
        except sqlite3.Error:
            return {}
    return _per_project_finding_counts(history_db, project_ids)


def _latest_scans(
    db: sqlite3.Connection,
    project_ids: list[str],
) -> dict[str, sqlite3.Row]:
    """Latest scan_history record per project (single indexed query)."""
    if not project_ids:
        return {}
    placeholders = ",".join("?" for _ in project_ids)
    rows = db.execute(
        "SELECT sh.* FROM scan_history sh "
        "JOIN ("
        "    SELECT project_id, MAX(scan_timestamp) AS max_ts "
        "    FROM scan_history "
        f"    WHERE project_id IN ({placeholders}) "
        "    GROUP BY project_id"
        ") latest ON latest.project_id = sh.project_id "
        "AND latest.max_ts = sh.scan_timestamp",
        project_ids,
    ).fetchall()
    return {row["project_id"]: row for row in rows}


def get_portfolio_rows(
    project_ids: list[str] | None = None,
    *,
    project_store: ProjectStore | None = None,
    history_db: sqlite3.Connection | None = None,
    finding_store: FindingStore | None = None,
) -> list[PortfolioProjectRow]:
    """Per-project rows for the dashboard; same filtering rules as get_portfolio.

    ``project_ids=None`` → all ACTIVE projects. Archived projects are excluded
    unless explicitly listed in ``project_ids``.
    """
    store = project_store or _default_project_store()
    projects = _resolve_projects(project_ids, store)
    if not projects:
        return []

    own_db = history_db is None
    db = history_db or _connect_history_db(store)
    try:
        ids = [p.id for p in projects]
        latest = _latest_scans(db, ids)
        per_project_counts = _finding_counts_for(finding_store, db, ids)
    finally:
        if own_db:
            db.close()

    rows: list[PortfolioProjectRow] = []
    for project in projects:
        open_findings, resolved_findings = per_project_counts.get(project.id, (0, 0))
        record = latest.get(project.id)
        if record is not None:
            rows.append(
                PortfolioProjectRow(
                    project_id=project.id,
                    project_name=project.name,
                    total_links=int(record["total_links"] or 0),
                    broken_count=int(record["broken_count"] or 0),
                    new_broken_count=int(record["new_broken_count"] or 0),
                    open_findings=open_findings,
                    resolved_findings=resolved_findings,
                    last_scan_timestamp=record["scan_timestamp"],
                    last_scan_status=record["status"] or "completed",
                    pinned=project.pinned,
                    archived=project.archived,
                )
            )
        else:
            rows.append(
                PortfolioProjectRow(
                    project_id=project.id,
                    project_name=project.name,
                    total_links=0,
                    broken_count=0,
                    new_broken_count=0,
                    open_findings=open_findings,
                    resolved_findings=resolved_findings,
                    last_scan_timestamp=None,
                    last_scan_status="never_run",
                    pinned=project.pinned,
                    archived=project.archived,
                )
            )
    return rows


def get_portfolio(
    project_ids: list[str] | None = None,
    *,
    project_store: ProjectStore | None = None,
    history_db: sqlite3.Connection | None = None,
    finding_store: FindingStore | None = None,
) -> PortfolioSummary:
    """Aggregate latest per-project scan records into a portfolio summary.

    ``project_ids=None`` → all ACTIVE projects. Archived projects are excluded
    unless explicitly listed in ``project_ids``.
    Returns PortfolioSummary (never raises on empty data).
    """
    store = project_store or _default_project_store()
    projects = _resolve_projects(project_ids, store)
    if not projects:
        return PortfolioSummary(
            projects=0,
            scanned_projects=0,
            unscanned_projects=0,
            total_links=0,
            broken_count=0,
            new_broken_count=0,
            open_findings=0,
            resolved_findings=0,
            health_score=100.0,
            last_scan_timestamp=None,
        )

    own_db = history_db is None
    db = history_db or _connect_history_db(store)
    try:
        ids = [p.id for p in projects]
        latest = _latest_scans(db, ids)
        open_findings, resolved_findings = _finding_counts(db, ids)
    finally:
        if own_db:
            db.close()

    scanned = 0
    total_links = 0
    broken_count = 0
    new_broken_count = 0
    last_scan_timestamp: str | None = None
    for record in latest.values():
        scanned += 1
        total_links += int(record["total_links"] or 0)
        broken_count += int(record["broken_count"] or 0)
        new_broken_count += int(record["new_broken_count"] or 0)
        timestamp = record["scan_timestamp"]
        if timestamp and (
            last_scan_timestamp is None or timestamp > last_scan_timestamp
        ):
            last_scan_timestamp = timestamp

    health_score = (
        round(100.0 * (1 - broken_count / total_links), 1) if total_links > 0 else 100.0
    )
    return PortfolioSummary(
        projects=len(projects),
        scanned_projects=scanned,
        unscanned_projects=len(projects) - scanned,
        total_links=total_links,
        broken_count=broken_count,
        new_broken_count=new_broken_count,
        open_findings=open_findings,
        resolved_findings=resolved_findings,
        health_score=health_score,
        last_scan_timestamp=last_scan_timestamp,
    )


def get_portfolio_trends(
    project_ids: list[str] | None = None,
    days: int = 30,
    *,
    project_store: ProjectStore | None = None,
    history_db: sqlite3.Connection | None = None,
) -> list[PortfolioTrendPoint]:
    """Daily broken-link trend across selected projects for the last ``days`` days.

    ``days <= 0`` → all history. Returns ascending list of {date, total_links,
    broken_count}; days with no records are omitted (chart fills gaps).
    """
    store = project_store or _default_project_store()
    projects = _resolve_projects(project_ids, store)
    if not projects:
        return []

    own_db = history_db is None
    db = history_db or _connect_history_db(store)
    try:
        ids = [p.id for p in projects]
        placeholders = ",".join("?" for _ in ids)
        rows = db.execute(
            "SELECT scan_timestamp, total_links, broken_count "
            "FROM scan_history "
            f"WHERE project_id IN ({placeholders}) "
            "ORDER BY scan_timestamp ASC",
            ids,
        ).fetchall()
    finally:
        if own_db:
            db.close()

    cutoff = None
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    daily: dict[str, list[int]] = {}
    for row in rows:
        timestamp = row["scan_timestamp"]
        if not timestamp:
            continue
        if cutoff is not None and timestamp < cutoff:
            continue
        day = timestamp[:10]
        bucket = daily.setdefault(day, [0, 0])
        bucket[0] += int(row["total_links"] or 0)
        bucket[1] += int(row["broken_count"] or 0)

    return [
        PortfolioTrendPoint(date=day, total_links=values[0], broken_count=values[1])
        for day, values in sorted(daily.items())
    ]


def portfolio_rows_to_dicts(rows: list[PortfolioProjectRow]) -> list[dict[str, Any]]:
    """Serialize portfolio rows for JSON responses."""
    return [asdict(row) for row in rows]
