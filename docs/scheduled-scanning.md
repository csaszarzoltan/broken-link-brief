# Scheduled Scanning

BrokenLinkBrief supports automated recurring scans through a scheduler that persists schedules in SQLite, leases work atomically, and detects regressions between scan runs.

## Overview

The scheduled scanning system adds:

- **Cron-based scheduling** — express scan frequency with standard 5-field cron expressions
- **SQLite persistence** — schedules survive process restarts
- **Atomic worker leasing** — prevent duplicate scans when multiple workers run
- **Regression detection** — compare current scan results against the last successful scan to surface newly broken links
- **Notification integration** — send regression alerts via email, Slack, or webhook

## Architecture

| Module | Purpose |
|--------|---------|
| `scheduler.py` | `SchedulerService` lifecycle, `ScheduleStore` for lightweight leasing, cron parsing |
| `scheduler_config.py` | YAML/JSON config validation, `ProjectConfig` dataclass |
| `scheduled_scan.py` | `ScheduledScanExecutor` — run scans with retry and result aggregation |
| `scan_history.py` | `ScanHistoryStore` — SQLite-backed scan history with pagination |
| `regression_detector.py` | `RegressionDetector` — compare scans, `RegressionNotifier` — format and send alerts |
| `scheduled_projects.py` | `aggregate_scheduled_projects()` — merge schedules with project metadata for dashboard views |

## Configuration File Format

Scheduled scanning is configured through a YAML or JSON file with `version: "1.0"` and a `projects` list.

### Minimal Example

```yaml
version: "1.0"

projects:
  - name: "My website"
    urls:
      - "https://example.com/"
    schedule:
      cron: "0 9 * * *"
      timezone: "UTC"
```

### Full Example

```yaml
version: "1.0"

projects:
  - name: "Production site"
    urls:
      - "https://example.com/"
      - "https://example.com/docs"
      - "https://example.com/api"
    schedule:
      cron: "0 */6 * * *"
      timezone: "Europe/Zurich"
    notifications:
      - type: email
        target: "team@example.com"
      - type: slack
        target: "#monitoring"
      - type: webhook
        target: "pagerduty"
        webhook_url: "https://events.pagerduty.com/integration/xxx/enqueue"
    options:
      timeout: 15.0
      max_workers: 10
```

### Configuration Reference

#### Project Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Human-readable project name (max 100 chars) |
| `urls` | list[string] | Yes | 1–50 target URLs (http/https, SSRF-validated) |
| `schedule.cron` | string | Yes | 5-field cron expression (see below) |
| `schedule.timezone` | string | Yes | IANA timezone name (e.g. `UTC`, `Europe/Zurich`) |
| `notifications` | list | No | Notification channels (email, slack, webhook) |
| `options.timeout` | float | No | Per-request timeout in seconds (default: 10.0) |
| `options.max_workers` | int | No | Max parallel workers (default: 3) |

#### Notification Channel Types

| Type | Fields | Description |
|------|--------|-------------|
| `email` | `target` (address) | Email notification via SMTP (requires env vars) |
| `slack` | `target` (channel) | Slack notification via Incoming Webhook (requires env var) |
| `webhook` | `target`, `webhook_url` | Generic webhook POST with HMAC signing |

## Cron Expression Reference

The scheduler uses standard 5-field cron syntax:

```
minute hour day_of_month month day_of_week
```

### Common Patterns

| Cron Expression | Frequency |
|----------------|-----------|
| `0 9 * * *` | Daily at 09:00 |
| `0 */4 * * *` | Every 4 hours |
| `0 9 * * 1` | Every Monday at 09:00 |
| `0 9 1 * *` | First day of each month at 09:00 |
| `*/15 * * * *` | Every 15 minutes |
| `0 9 * * 1-5` | Weekdays at 09:00 |

### Field Ranges

| Field | Min | Max |
|-------|-----|-----|
| minute | 0 | 59 |
| hour | 0 | 23 |
| day of month | 1 | 31 |
| month | 1 | 12 |
| day of week | 0 | 7 (0 and 7 = Sunday) |

## Loading and Validating Configuration

### From YAML

```python
from pathlib import Path
from brokenlinkbrief.scheduler_config import load_projects_config

configs = load_projects_config(Path("schedule-config.yaml"))
for config in configs:
    print(f"Scheduled: {config.name} ({config.schedule.cron})")
```

### From Python Dict

```python
from brokenlinkbrief.scheduler_config import validate_project_config

config = validate_project_config(
    {
        "name": "My project",
        "urls": ["https://example.com/"],
        "schedule": {"cron": "0 9 * * *", "timezone": "UTC"},
    }
)
```

### Validation Rules

- `name`: Required, non-empty, max 100 characters
- `urls`: 1–50 entries, each with http/https scheme and non-empty host
- `schedule.cron`: Exactly 5 fields, values in range
- `schedule.timezone`: Must be valid IANA timezone (e.g. `Europe/Zurich`)
- `notifications.type`: One of `email`, `slack`, `webhook`
- Webhook notifications require `webhook_url`

## Running the Scheduler

### Using SchedulerService

```python
from brokenlinkbrief.scheduler import SchedulerService, ProjectSchedule

service = SchedulerService(db_path="scheduler.db")
service.start()

# Add a project schedule
service.add_project(
    ProjectSchedule(
        project_id="docs",
        name="Documentation",
        cron_expression="*/30 * * * *",
        timezone="UTC",
        urls=["https://docs.example.com/"],
        enabled=True,
    )
)

# List scheduled projects
for project in service.list_projects():
    print(f"{project.project_id}: {project.cron_expression} ({project.timezone})")

# Check what's due
due = service.get_next_run_times()

service.stop()
```

### Using ScheduleStore (Lightweight Leasing)

```python
from brokenlinkbrief.scheduler import ScheduleStore

store = ScheduleStore("schedules.db")
store.create("my-project", "0 9 * * *", "UTC", next_due_at=0)

# Atomically claim due schedules
due = store.claim_due(now=time.time(), worker_id="worker-1")
for schedule in due:
    print(f"Running: {schedule.project_id}")
```

## Regression Detection

The `RegressionDetector` compares current scan results against the last successful scan:

```python
from brokenlinkbrief.regression_detector import RegressionDetector

detector = RegressionDetector()

# Compare current scan against history
report = detector.detect(
    project_id="my-project",
    current_results={
        "https://example.com/": [
            {
                "url": "https://example.com/old-page",
                "status": 404,
                "reason": "Not Found",
            },
            {"url": "https://example.com/good-page", "status": 200, "reason": "OK"},
        ]
    },
    scan_history=previous_scan_results,  # list of scan dicts
)

if report.has_regressions:
    print(f"New broken links: {len(report.new_broken)}")
    print(f"Resolved: {len(report.resolved)}")
    print(report.format_alert())  # Human-readable alert
```

### Regression Report Fields

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | string | Project identifier |
| `scan_id` | string | Current scan ID |
| `previous_scan_id` | string | ID of the previous scan used for comparison |
| `new_broken` | list[dict] | Newly broken links (url, status, reason, previous_status) |
| `resolved` | list[dict] | Links that are no longer broken |
| `status_changes` | list[dict] | Links whose error status changed (still broken) |
| `has_regressions` | bool | True if any new broken links or status changes |

## Executing Scheduled Scans

`ScheduledScanExecutor` orchestrates a scan for a project with retry logic:

```python
from brokenlinkbrief.scheduled_scan import ScheduledScanExecutor

executor = ScheduledScanExecutor(max_retries=3, retry_delay=1.0)

result = executor.execute_scan(
    {
        "id": "my-project",
        "name": "My website",
        "urls": ["https://example.com/", "https://example.com/docs"],
        "options": {"timeout": 10.0, "max_workers": 5},
    }
)

print(f"Status: {result.status}")
print(f"Links checked: {result.total_links}")
print(f"Broken: {result.broken_count}")
print(f"Duration: {result.duration_seconds:.1f}s")
if result.errors:
    print(f"Errors: {result.errors}")
```

### ScanResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `scan_id` | string | Unique scan execution ID |
| `project_id` | string | Project identifier |
| `project_name` | string | Human-readable project name |
| `scan_timestamp` | string | ISO 8601 UTC timestamp |
| `urls_scanned` | int | Number of target URLs scanned |
| `total_links` | int | Total links discovered |
| `broken_count` | int | Broken links in this scan |
| `new_broken_count` | int | Newly broken links (regressions) |
| `status` | string | `completed`, `partial`, or `failed` |
| `raw_results` | dict | Per-URL link results |
| `regression_flags` | list[str] | Human-readable regression descriptions |
| `duration_seconds` | float | Wall-clock scan time |
| `errors` | list[str] | Error messages if any |

## Scan History

`ScanHistoryStore` persists scan results in SQLite for regression comparison:

```python
import sqlite3
from brokenlinkbrief.scan_history import ScanHistoryStore

db = sqlite3.connect("history.db")
db.row_factory = sqlite3.Row
store = ScanHistoryStore(db)

# Record a scan
record = store.record_scan(
    project_id="my-project",
    total_urls=2,
    total_links=45,
    broken_count=3,
    raw_results=[{"url": "...", "status": 404}],
)

# Query history
latest = store.get_latest_scan("my-project")
history = store.get_scan_history("my-project", limit=10)
```

## Deploying with Cron

### Systemd Timer (recommended for single-host)

Create a service unit:

```ini
# /etc/systemd/system/brokenlinkbrief-scan.service
[Unit]
Description=BrokenLinkBrief Scheduled Scan
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/opt/broken-link-brief
ExecStart=/opt/broken-link-brief/.venv/bin/python -m brokenlinkbrief.app --schedule --config /etc/brokenlinkbrief/schedule-config.yaml
Environment=BROKENLINKBRIEF_PROJECT_DB=/var/lib/brokenlinkbrief/scheduler.db
Environment=BROKENLINKBRIEF_SCAN_TOKEN=your-token-here
```

Create a timer unit:

```ini
# /etc/systemd/system/brokenlinkbrief-scan.timer
[Unit]
Description=Run BrokenLinkBrief scan every hour

[Timer]
OnCalendar=*-*-* *:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brokenlinkbrief-scan.timer
```

### Docker (single container with cron)

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .

COPY examples/schedule-config.yaml /etc/brokenlinkbrief/schedule-config.yaml
COPY docker/crontab /etc/cron.d/brokenlinkbrief

RUN chmod 0644 /etc/cron.d/brokenlinkbrief && crontab /etc/cron.d/brokenlinkbrief

CMD ["cron", "-f"]
```

Docker crontab:

```
# /docker/crontab
0 * * * * cd /app && .venv/bin/python -m brokenlinkbrief.app --schedule --config /etc/brokenlinkbrief/schedule-config.yaml >> /var/log/brokenlinkbrief.log 2>&1
```

Build and run with a persistent volume for the database:

```bash
docker build -t brokenlinkbrief .
docker run -d \
  -v blb-data:/var/lib/brokenlinkbrief \
  -e BROKENLINKBRIEF_PROJECT_DB=/var/lib/brokenlinkbrief/scheduler.db \
  brokenlinkbrief
```

### Bare Metal (crontab)

```bash
# Edit crontab
crontab -e

# Add entry — scan daily at 09:00 UTC
0 9 * * * cd /opt/broken-link-brief && .venv/bin/python -m brokenlinkbrief.app --schedule --config /opt/broken-link-brief/schedule-config.yaml >> /var/log/blb-scan.log 2>&1
```

### Docker Compose

```yaml
version: "3.8"

services:
  brokenlinkbrief:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - blb-data:/var/lib/brokenlinkbrief
    environment:
      - BROKENLINKBRIEF_PROJECT_DB=/var/lib/brokenlinkbrief/scheduler.db
      - BROKENLINKBRIEF_SCAN_TOKEN=${BLB_SCAN_TOKEN}
      - BROKENLINKBRIEF_SMTP_HOST=${SMTP_HOST}
      - BROKENLINKBRIEF_SMTP_PORT=587
      - BROKENLINKBRIEF_SMTP_USER=${SMTP_USER}
      - BROKENLINKBRIEF_SMTP_PASSWORD=${SMTP_PASSWORD}
      - BROKENLINKBRIEF_SMTP_FROM=${SMTP_FROM}
      - BROKENLINKBRIEF_SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}

  scanner:
    build: .
    volumes:
      - blb-data:/var/lib/brokenlinkbrief
    environment:
      - BROKENLINKBRIEF_PROJECT_DB=/var/lib/brokenlinkbrief/scheduler.db
    entrypoint: ["cron", "-f"]
    depends_on:
      - brokenlinkbrief

volumes:
  blb-data:
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKENLINKBRIEF_PROJECT_DB` | `.brokenlinkbrief.db` | SQLite database path for scheduler and projects |
| `BROKENLINKBRIEF_HISTORY_DIR` | `.history/` | Directory for JSONL scan history |

## Troubleshooting

### "cron expression is invalid"

Ensure the cron expression has exactly 5 whitespace-separated fields and values are in range (minute 0–59, hour 0–23, etc.).

### "timezone is invalid"

Use a valid IANA timezone name. Common ones: `UTC`, `Europe/Zurich`, `America/New_York`, `Asia/Tokyo`.

### Stale `.pyc` cache

After upgrading, clear Python bytecode cache:

```bash
find . -type d -name __pycache__ -exec rm -rf {} +
```

### Database locked

If you see `sqlite3.OperationalError: database is locked`, ensure only one scheduler process writes to the same database file. The `ScheduleStore` uses `BEGIN IMMEDIATE` to handle concurrent access, but multiple writers to the same SQLite file are inherently serialized.
