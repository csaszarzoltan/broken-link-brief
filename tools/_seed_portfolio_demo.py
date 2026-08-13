"""Seed a demo project DB + scan history, then boot the app and curl portfolio endpoints.

Usage: BROKENLINKBRIEF_PROJECT_DB=/tmp/pf.db .venv/bin/python tools/_seed_portfolio_demo.py
"""

import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "src")

from brokenlinkbrief.projects import ProjectStore  # noqa: E402
from brokenlinkbrief.scan_history import ScanHistoryStore  # noqa: E402

DB = os.environ.get("BROKENLINKBRIEF_PROJECT_DB", "/tmp/pf_demo.db")
PORT = os.environ.get("PF_PORT", "8765")
TOKEN = "demo-token"


def main() -> None:
    if os.path.exists(DB):
        os.remove(DB)
    store = ProjectStore(DB)
    alpha = store.create("Docs site", ["https://docs.example.com/"])
    beta = store.create("Marketing site", ["https://www.example.com/"])
    store.create("Unscanned project", ["https://staging.example.com/"])

    # scan_history table lives in the same project DB (production layout)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute(
        """CREATE TABLE IF NOT EXISTS scan_history (
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
        )"""
    )
    history = ScanHistoryStore(db)
    # older scan for alpha -> only latest counts
    history.record_scan(
        alpha.id, total_urls=12, total_links=40, broken_count=3, new_broken_count=1
    )
    history.record_scan(
        alpha.id, total_urls=14, total_links=50, broken_count=5, new_broken_count=2
    )
    history.record_scan(
        beta.id, total_urls=6, total_links=20, broken_count=8, new_broken_count=0
    )
    db.commit()
    db.close()

    print(f"seeded {DB}")
    print(f"alpha={alpha.id} beta={beta.id}")
    print(f"alpha name={alpha.name}")


def fetch(path: str) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def probe(server_pid: int) -> None:
    """Wait for server then print real responses (used by the docs example)."""
    for _ in range(50):
        try:
            fetch("/health")
            break
        except Exception:
            time.sleep(0.2)
    print("\n=== GET /api/portfolio (token) ===")
    status, body = fetch(f"/api/portfolio?token={TOKEN}")
    print(status, body[:1600])
    print("\n=== GET /api/portfolio/summary?days=30 (token) ===")
    status, body = fetch(f"/api/portfolio/summary?days=30&token={TOKEN}")
    print(status, body[:1200])
    print("\n=== GET /api/portfolio (no token) ===")
    status, body = fetch("/api/portfolio")
    print(status, body[:200])


if __name__ == "__main__":
    main()
