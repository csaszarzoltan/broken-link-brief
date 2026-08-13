"""Source-aware link occurrences and repair workflow."""
from __future__ import annotations

import html
import sqlite3
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


@dataclass(frozen=True)
class LinkOccurrence:
    """A link as it appeared in a source page."""

    source_url: str
    target_url: str
    anchor_text: str
    context: str


class _AnchorParser(HTMLParser):
    """Collect anchor occurrences while parsing a source document."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.items: list[LinkOccurrence] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data) -> None:
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag) -> None:
        if tag.lower() == "a" and self.href is not None:
            target = urljoin(self.source, html.unescape(self.href))
            anchor = " ".join("".join(self.text).split())
            self.items.append(
                LinkOccurrence(
                    self.source,
                    target,
                    anchor,
                    f'<a href="{self.href}">{anchor}</a>',
                )
            )
            self.href = None
            self.text = []


def extract_occurrences(source_url: str, body: str) -> list[LinkOccurrence]:
    """Return all anchor occurrences found in the given HTML body."""
    parser = _AnchorParser(source_url)
    parser.feed(body)
    return parser.items


@dataclass(frozen=True)
class Finding:
    """A recorded finding for a link occurrence."""

    id: str
    occurrence: LinkOccurrence
    status: int | None


@dataclass(frozen=True)
class RepairTask:
    """A repair assignment for a finding."""

    finding_id: str
    assignee: str
    state: str


class FindingStore:
    """Persistent storage for findings and repair tasks."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, "
                "source TEXT, target TEXT, anchor TEXT, context TEXT, status INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS tasks (finding_id TEXT PRIMARY KEY, "
                "assignee TEXT, state TEXT)"
            )

    def record(self, occurrence: LinkOccurrence, status: int | None) -> Finding:
        """Record a finding for an occurrence."""
        fid = uuid.uuid4().hex
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO findings VALUES (?,?,?,?,?,?)",
                (
                    fid,
                    occurrence.source_url,
                    occurrence.target_url,
                    occurrence.anchor_text,
                    occurrence.context,
                    status,
                ),
            )
        return Finding(fid, occurrence, status)

    def assign(self, finding_id: str, assignee: str) -> RepairTask:
        """Assign a finding to an assignee; raises on unknown or duplicate."""
        if not assignee.strip():
            raise ValueError("assignee required")
        with sqlite3.connect(self.path) as db:
            if not db.execute(
                "SELECT 1 FROM findings WHERE id=?", (finding_id,)
            ).fetchone():
                raise KeyError(finding_id)
            try:
                db.execute(
                    "INSERT INTO tasks VALUES (?,?,'ASSIGNED')",
                    (finding_id, assignee),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("TRIAGE_ASSIGNMENT_CONFLICT") from exc
        return RepairTask(finding_id, assignee, "ASSIGNED")
