"""Scheduled projects dashboard view."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScheduledProjectView:
    """A single scheduled project as displayed on the dashboard."""
    project_id: str
    project_name: str
    cadence: str
    timezone: str
    state: str
    next_due_at: float
    last_scan_timestamp: str | None = None
    last_scan_broken_count: int | None = None
    last_scan_status: str = "never_run"


def aggregate_scheduled_projects(
    schedules: list[Any],
    projects: list[Any],
    scan_history_store: Any | None,
) -> list[ScheduledProjectView]:
    """Merge schedules, project metadata, and scan history into dashboard views.

    Args:
        schedules: List of Schedule dataclass instances.
        projects: List of Project dataclass instances (for name lookup).
        scan_history_store: ScanHistoryStore instance (or None).

    Returns:
        List of ScheduledProjectView sorted by next_due_at.
    """
    # Build project name lookup
    name_map: dict[str, str] = {}
    for p in projects:
        # Handle both real objects and MagicMock objects
        pid = None
        pname = None
        if hasattr(p, "project_id"):
            pid_val = p.project_id
            if isinstance(pid_val, str):
                pid = pid_val
        if not pid and hasattr(p, "id"):
            id_val = p.id
            if isinstance(id_val, str):
                pid = id_val
        if not pid and isinstance(p, dict):
            pid = p.get("id")

        if hasattr(p, "name"):
            name_val = p.name
            if isinstance(name_val, str):
                pname = name_val
        if not pname and isinstance(p, dict):
            pname = p.get("name")
        if pid and pname:
            name_map[pid] = pname

    views: list[ScheduledProjectView] = []
    for sched in schedules:
        pid = getattr(sched, "project_id", None) or (sched.get("project_id") if isinstance(sched, dict) else "")
        if not pid:
            continue
        pname = name_map.get(pid)
        if not pname:
            # Skip schedules without matching project
            continue
        cadence = getattr(sched, "cadence", None) or (sched.get("cadence", "") if isinstance(sched, dict) else "")
        tz = getattr(sched, "timezone", None) or (sched.get("timezone", "UTC") if isinstance(sched, dict) else "UTC")
        state = getattr(sched, "state", None) or (sched.get("state", "ACTIVE") if isinstance(sched, dict) else "ACTIVE")
        next_due = getattr(sched, "next_due_at", None) or (sched.get("next_due_at", 0.0) if isinstance(sched, dict) else 0.0)

        last_ts = None
        last_broken = None
        last_status = "never_run"
        if scan_history_store is not None and hasattr(scan_history_store, "get_latest_scan"):
            latest = scan_history_store.get_latest_scan(pid)
            if latest is not None:
                last_ts = latest.scan_timestamp
                last_broken = latest.broken_count
                last_status = latest.status

        views.append(ScheduledProjectView(
            project_id=pid,
            project_name=pname,
            cadence=cadence,
            timezone=tz,
            state=state,
            next_due_at=next_due,
            last_scan_timestamp=last_ts,
            last_scan_broken_count=last_broken,
            last_scan_status=last_status,
        ))

    return sorted(views, key=lambda v: v.next_due_at)
