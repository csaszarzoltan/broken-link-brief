"""Diff detection for link state changes between scans.

Compares current scan results against persisted link state
and produces a DiffReport with per-URL change categories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brokenlinkbrief.link_state import LinkStateStore


@dataclass(frozen=True)
class DiffReport:
    """Report summarizing link diff between two scan states."""

    project_id: str
    target_url: str
    timestamp: str
    new_broken: list[dict[str, Any]] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    status_changes: list[dict[str, Any]] = field(default_factory=list)
    new_links: list[dict[str, Any]] = field(default_factory=list)
    removed_links: list[dict[str, Any]] = field(default_factory=list)
    has_changes: bool = False


class DiffDetector:
    """Detects link state changes by comparing current scan against persisted state."""

    def __init__(self, link_state_store: LinkStateStore) -> None:
        self._store = link_state_store

    def compare(
        self,
        project_id: str,
        target_url: str,
        current_links: list[dict[str, Any]],
    ) -> DiffReport:
        """Compare current scan results against persisted link state.

        Args:
            project_id: Project identifier.
            target_url: The page URL that was scanned.
            current_links: List of link result dicts from current scan.

        Returns:
            DiffReport with all change categories.
        """
        ts = datetime.now(timezone.utc).isoformat()

        current_by_url: dict[str, dict[str, Any]] = {}
        for link in current_links:
            url = link.get("url", "")
            if url:
                current_by_url[url] = link

        # Build previous lookup from the store
        prev_by_url: dict[str, dict[str, Any]] = {}
        try:
            previous_states = self._store.get_link_states(
                project_id, target_url
            )
            for state in previous_states:
                url = state.link_url
                if url not in prev_by_url:
                    prev_by_url[url] = {
                        "url": url,
                        "status": state.status,
                        "reason": state.reason,
                    }
        except Exception:
            pass

        return self._compute_diff(
            project_id, target_url, ts, current_by_url, prev_by_url
        )

    def compare_with_previous(
        self,
        project_id: str,
        target_url: str,
        current_links: list[dict[str, Any]],
        previous_links: list[dict[str, Any]],
    ) -> DiffReport:
        """Compare current scan against explicitly provided previous scan data.

        Args:
            project_id: Project identifier.
            target_url: The page URL that was scanned.
            current_links: List of link result dicts from current scan.
            previous_links: List of link result dicts from previous scan.

        Returns:
            DiffReport with all change categories.
        """
        ts = datetime.now(timezone.utc).isoformat()

        current_by_url: dict[str, dict[str, Any]] = {}
        for link in current_links:
            url = link.get("url", "")
            if url:
                current_by_url[url] = link

        prev_by_url: dict[str, dict[str, Any]] = {}
        for link in previous_links:
            url = link.get("url", "")
            if url and url not in prev_by_url:
                prev_by_url[url] = link

        return self._compute_diff(
            project_id, target_url, ts, current_by_url, prev_by_url
        )

    def _compute_diff(
        self,
        project_id: str,
        target_url: str,
        timestamp: str,
        current_by_url: dict[str, dict[str, Any]],
        prev_by_url: dict[str, dict[str, Any]],
    ) -> DiffReport:
        """Core diff logic shared by compare() and compare_with_previous()."""
        has_previous = bool(prev_by_url)

        new_broken: list[dict[str, Any]] = []
        resolved: list[dict[str, Any]] = []
        status_changes: list[dict[str, Any]] = []
        new_links: list[dict[str, Any]] = []
        removed_links: list[dict[str, Any]] = []

        all_urls = set(current_by_url.keys()) | set(prev_by_url.keys())

        for url in sorted(all_urls):
            curr = current_by_url.get(url)
            prev = prev_by_url.get(url)
            category, entry = self._classify_link(url, curr, prev)
            if category == "new":
                if has_previous:
                    new_links.append(entry)
            elif category == "removed":
                removed_links.append(entry)
            elif category == "new_broken":
                new_broken.append(entry)
            elif category == "resolved":
                resolved.append(entry)
            elif category == "status_change":
                status_changes.append(entry)

        # Currently-broken links not in previous scan
        for url, link_data in current_by_url.items():
            status = link_data.get("status")
            reason = link_data.get("reason")
            is_broken = (status is not None and status >= 400) or (
                status is None and reason is not None
            )
            if is_broken and url not in prev_by_url:
                existing_urls = {e["url"] for e in new_broken}
                if url not in existing_urls:
                    entry_new: dict[str, Any] = {"url": url, "status": status}
                    if reason:
                        entry_new["reason"] = reason
                    new_broken.append(entry_new)

        has_changes = bool(
            new_broken or resolved or status_changes or new_links or removed_links
        )

        return DiffReport(
            project_id=project_id,
            target_url=target_url,
            timestamp=timestamp,
            new_broken=new_broken,
            resolved=resolved,
            status_changes=status_changes,
            new_links=new_links,
            removed_links=removed_links,
            has_changes=has_changes,
        )

    @staticmethod
    def _classify_link(
        url: str,
        curr: dict[str, Any] | None,
        prev: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any]]:
        """Classify a single URL's change between current and previous state.

        Returns a (category, entry) pair. Category is one of:
        "new", "removed", "new_broken", "resolved", "status_change" or "none".
        """
        curr_status = curr.get("status") if curr else None
        curr_reason = curr.get("reason") if curr else None
        prev_status = prev.get("status") if prev else None
        prev_reason = prev.get("reason") if prev else None

        curr_broken = (curr_status is not None and curr_status >= 400) or (
            curr_status is None and curr is not None and curr_reason is not None
        )
        prev_broken = (prev_status is not None and prev_status >= 400) or (
            prev_status is None and prev is not None and prev_reason is not None
        )

        if prev is None and curr is not None:
            return "new", {
                "url": url,
                "status": curr_status,
                "reason": curr_reason,
            }
        if prev is not None and curr is None:
            return "removed", {
                "url": url,
                "status": prev_status,
                "reason": prev_reason,
            }
        if prev is not None and curr is not None:
            if not prev_broken and curr_broken:
                # Was healthy, now broken → new_broken
                entry: dict[str, Any] = {"url": url, "status": curr_status}
                if curr_reason:
                    entry["reason"] = curr_reason
                if prev_status is not None:
                    entry["previous_status"] = prev_status
                return "new_broken", entry
            if prev_broken and not curr_broken:
                # Was broken, now healthy → resolved
                return "resolved", {
                    "url": url,
                    "previous_status": prev_status,
                    "current_status": curr_status,
                }
            if prev_broken and curr_broken and prev_status != curr_status:
                # Both broken but different status → status_change
                return "status_change", {
                    "url": url,
                    "previous_status": prev_status,
                    "current_status": curr_status,
                }
        return "none", {}
