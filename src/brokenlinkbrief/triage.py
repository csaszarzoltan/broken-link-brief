"""Source-aware link occurrences and repair workflow."""
from __future__ import annotations

import html
import re
import sqlite3
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


@dataclass(frozen=True)
class LinkOccurrence:
    source_url: str
    target_url: str
    anchor_text: str
    context: str


class _AnchorParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True); self.source=source; self.items=[]; self.href=None; self.text=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a": self.href=dict(attrs).get("href"); self.text=[]
    def handle_data(self, data):
        if self.href is not None: self.text.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=="a" and self.href is not None:
            target=urljoin(self.source, html.unescape(self.href)); anchor=" ".join("".join(self.text).split())
            self.items.append(LinkOccurrence(self.source,target,anchor,f'<a href="{self.href}">{anchor}</a>'))
            self.href=None; self.text=[]


def extract_occurrences(source_url: str, body: str) -> list[LinkOccurrence]:
    parser=_AnchorParser(source_url); parser.feed(body); return parser.items


@dataclass(frozen=True)
class Finding: id: str; occurrence: LinkOccurrence; status: int | None
@dataclass(frozen=True)
class RepairTask: finding_id: str; assignee: str; state: str


class FindingStore:
    def __init__(self, path: str | Path) -> None:
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, source TEXT, target TEXT, anchor TEXT, context TEXT, status INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS tasks (finding_id TEXT PRIMARY KEY, assignee TEXT, state TEXT)")
    def record(self, occurrence: LinkOccurrence, status: int | None) -> Finding:
        fid=uuid.uuid4().hex
        with sqlite3.connect(self.path) as db: db.execute("INSERT INTO findings VALUES (?,?,?,?,?,?)",(fid,occurrence.source_url,occurrence.target_url,occurrence.anchor_text,occurrence.context,status))
        return Finding(fid,occurrence,status)
    def assign(self, finding_id: str, assignee: str) -> RepairTask:
        if not assignee.strip(): raise ValueError("assignee required")
        with sqlite3.connect(self.path) as db:
            if not db.execute("SELECT 1 FROM findings WHERE id=?",(finding_id,)).fetchone(): raise KeyError(finding_id)
            try: db.execute("INSERT INTO tasks VALUES (?,?,'ASSIGNED')",(finding_id,assignee))
            except sqlite3.IntegrityError as exc: raise ValueError("TRIAGE_ASSIGNMENT_CONFLICT") from exc
        return RepairTask(finding_id,assignee,"ASSIGNED")
