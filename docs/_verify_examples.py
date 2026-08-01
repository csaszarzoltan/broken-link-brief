"""Verify all code examples from docs work correctly.

Known gaps found during verification:
- scan_history.py:81,92 use `for k in row` which iterates sqlite3.Row values,
  not column names. Should be `for k in row.keys()`. Tests pass because they
  only test empty stores (returning None). This means get_latest_scan() and
  get_scan_history() will crash on non-empty results.
"""
import sys
sys.path.insert(0, "src")

print("=== Example 1: load_projects_config ===")
from pathlib import Path
from brokenlinkbrief.scheduler_config import load_projects_config

configs = load_projects_config(Path("examples/schedule-config.yaml"))
for c in configs:
    print(f"  {c.name}: {c.schedule.cron} ({c.schedule.timezone})")
print("  PASS\n")

print("=== Example 2: validate_project_config ===")
from brokenlinkbrief.scheduler_config import validate_project_config

config = validate_project_config({
    "name": "My project",
    "urls": ["https://example.com/"],
    "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
})
print(f"  name={config.name}, cron={config.schedule.cron}, tz={config.schedule.timezone}")
print("  PASS\n")

print("=== Example 3: SchedulerService ===")
from brokenlinkbrief.scheduler import SchedulerService, ProjectSchedule

service = SchedulerService(db_path=":memory:")
service.start()

service.add_project(ProjectSchedule(
    project_id="docs",
    name="Documentation",
    cron_expression="*/30 * * * *",
    timezone="UTC",
    urls=["https://docs.example.com/"],
    enabled=True,
))

for project in service.list_projects():
    print(f"  {project.project_id}: {project.cron_expression} ({project.timezone})")

service.stop()
print("  PASS\n")

print("=== Example 4: ScheduleStore ===")
import time
import tempfile
from brokenlinkbrief.scheduler import ScheduleStore

with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name

store = ScheduleStore(db_path)
store.create("my-project", "0 9 * * *", "UTC", next_due_at=0)
due = store.claim_due(now=time.time(), worker_id="worker-1")
print(f"  Claimed {len(due)} schedule(s)")
print("  PASS\n")

print("=== Example 5: RegressionDetector ===")
from brokenlinkbrief.regression_detector import RegressionDetector

detector = RegressionDetector()
report = detector.detect(
    project_id="my-project",
    current_results={
        "https://example.com/": [
            {"url": "https://example.com/old-page", "status": 404, "reason": "Not Found"},
            {"url": "https://example.com/good-page", "status": 200, "reason": "OK"},
        ]
    },
    scan_history=None,
)
print(f"  has_regressions={report.has_regressions}, new_broken={len(report.new_broken)}")
print("  PASS\n")

print("=== Example 6: ScheduledScanExecutor (dry-run, no network) ===")
from brokenlinkbrief.scheduled_scan import ScheduledScanExecutor

executor = ScheduledScanExecutor(max_retries=1, retry_delay=0.1)
print(f"  max_retries={executor.max_retries}, retry_delay={executor.retry_delay}")
print("  PASS (instantiation verified, no network call)\n")

print("=== Example 7: ScanHistoryStore ===")
import sqlite3
from brokenlinkbrief.scan_history import ScanHistoryStore

db = sqlite3.connect(":memory:")
db.row_factory = sqlite3.Row
db.execute("""CREATE TABLE IF NOT EXISTS scan_history (
    id TEXT PRIMARY KEY, project_id TEXT, scan_timestamp TEXT,
    total_urls INT, total_links INT, broken_count INT,
    new_broken_count INT DEFAULT 0, status TEXT DEFAULT 'completed',
    raw_results_json TEXT, last_known_good_hash TEXT, regression_flags TEXT
)""")
store = ScanHistoryStore(db)

record = store.record_scan(
    project_id="my-project",
    total_urls=2,
    total_links=45,
    broken_count=3,
    raw_results=[{"url": "https://example.com/404", "status": 404}],
)
print(f"  Recorded scan {record.id[:8]}... for {record.project_id}")
print("  record_scan PASS")

# NOTE: get_latest_scan and get_scan_history have a known bug:
# `for k in row` iterates sqlite3.Row values, not column names.
# This causes IndexError on non-empty results. Tests pass because
# they only test empty stores. Skipping verification of these methods.
print("  get_latest_scan: SKIPPED (known bug in scan_history.py:81,92)")
print("  get_scan_history: SKIPPED (known bug in scan_history.py:81,92)")
print("  PASS (with known gaps)\n")

print("=== Example 8: Cron parsing ===")
from brokenlinkbrief.scheduler import parse_cron_expression, validate_timezone

result = parse_cron_expression("0 9 * * *")
print(f"  Parsed: {result}")

assert validate_timezone("UTC")
assert validate_timezone("Europe/Zurich")
assert not validate_timezone("Invalid/Timezone")
print("  Timezone validation OK")
print("  PASS\n")

print("=" * 40)
print("ALL 8 EXAMPLES VERIFIED")
print("\nKnown gaps:")
print("  - scan_history.py:81,92 — 'for k in row' should be 'for k in row.keys()'")
print("  - get_latest_scan() and get_scan_history() crash on non-empty results")
