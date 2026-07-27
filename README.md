# BrokenLinkBrief

A compact stdlib-based service that scans a page for links, checks their HTTP status, and exports a shareable brief (JSON, CSV, markdown, or JSONL).

## Features

- 🔍 Scan any webpage for broken links
- 📊 Export as JSON, CSV, Markdown, or JSONL
- ⚡ Batch scanning — check up to 50 URLs in parallel in a single request
- 🔔 Webhook notifications when broken links are found
- 📧 Email notifications via SMTP when broken links are detected
- 💬 Slack integration via Incoming Webhooks
- 🔒 Optional token-based authentication
- 📝 JSONL usage logging for analytics
- 🛡️ SSRF protection for URL validation

## Quick Start

```bash
# Install
pip install -e .

# Run
python -m brokenlinkbrief.app

# Scan a page
curl "http://127.0.0.1:8000/scan?url=https://example.com"
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Smoke test |
| GET | `/scan?url=<target>` | Optional | JSON results (default) |
| GET | `/scan?url=<target>&format=csv` | Optional | CSV export |
| GET | `/scan?url=<target>&format=markdown` | Optional | Markdown brief |
| GET | `/scan?url=<target>&format=jsonl` | Optional | JSON Lines |
| POST | `/scan-batch` | Optional | Batch scan up to 50 URLs |
| POST | `/webhooks` | Required | Register a webhook URL |
| GET | `/webhooks` | Required | List registered webhooks |
| DELETE | `/webhooks/<id>` | Required | Remove a webhook |

## Batch Scanning

Scan multiple pages for broken links in a single request. All URLs are checked concurrently using a thread pool, with results returned per-URL and as an aggregated summary.

### Basic Usage

```bash
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com", "https://httpstat.us/404"]}'
```

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `urls` | `list[string]` | Yes | URLs to scan (1–50 unique URLs) |
| `concurrency` | `int` | No | Max parallel workers (default 10, max 20) |
| `format` | `string` | No | Output format: `json` (default), `csv`, `markdown`, `jsonl` |

### Response Format (JSON)

The default JSON response contains per-URL results and an aggregated summary:

```json
{
  "results": {
    "https://example.com": [
      {
        "url": "https://example.com/link1",
        "status": 200,
        "reason": "OK",
        "location": null
      }
    ],
    "https://httpstat.us/404": [
      {
        "url": "https://httpstat.us/404",
        "status": 404,
        "reason": "Not Found",
        "location": null
      }
    ]
  },
  "summary": {
    "total_urls": 2,
    "broken_count": 1,
    "latency_seconds": 1.234
  }
}
```

Each value under `results` is an array of `LinkResult` objects for that URL (one per discovered link on the page).

### Concurrency Control

Control how many URLs are scanned in parallel by setting `concurrency` in the request body:

```bash
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "concurrency": 5}'
```

The `concurrency` value is capped at 20. If omitted, defaults to 10.

### Output Formats

Batch scans support the same output formats as single scans. For non-JSON formats, results from all URLs are flattened into a single table:

```bash
# CSV output
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "csv"}'

# Markdown output
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "markdown"}'

# JSONL output
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"], "format": "jsonl"}'
```

### Authentication

If `BROKENLINKBRIEF_SCAN_TOKEN` is set, pass the token as an `Authorization` header or a `token` query parameter:

```bash
curl -X POST http://127.0.0.1:8000/scan-batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ***" \
  -d '{"urls": ["https://example.com"]}'
```

### Error Responses

| Status | Condition |
|--------|-----------|
| 400 | Missing `urls` field, empty list, duplicate URLs, >50 URLs, or SSRF-blocked URL |
| 401 | Missing or invalid token (when `BROKENLINKBRIEF_SCAN_TOKEN` is set) |

Example error:

```json
{
  "detail": "duplicate URLs in request"
}
```

## Authentication

Set `BROKENLINKBRIEF_SCAN_TOKEN` to require a matching token on `/scan`, `/scan-batch`, and `/webhooks`.

## Webhook Notifications

Register an HTTPS webhook URL to receive notifications when broken links are detected during scans.

### Register a Webhook

```bash
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ***" \
  -d '{"url": "https://your-server.com/webhook", "secret": "optional-hmac-secret"}'
```

Response (201 Created):
```json
{
  "id": "a1b2c3d4e5f6",
  "url": "https://your-server.com/webhook"
}
```

### Payload Schema

When broken links are found, a POST request is sent to your webhook URL with this JSON payload:

```json
{
  "scanned_url": "https://example.com",
  "broken_links": [
    {
      "url": "https://example.com/missing",
      "status": 404,
      "reason": "Not Found"
    }
  ],
  "timestamp": "2026-07-21T12:00:00+00:00",
  "total_links": 42
}
```

### Verifying Signatures

If you provided a `secret` when registering the webhook, every delivery includes an `X-Webhook-Signature` header containing an HMAC-SHA256 hex digest of the payload.

Verify the signature in Python:

```python
import hmac
import hashlib

def verify_webhook_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    """Timing-safe verification of webhook signature."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Retry Behavior

Failed webhook deliveries are retried up to 3 times with exponential backoff:
- Attempt 1: immediate
- Attempt 2: 1 second delay
- Attempt 3: 2 seconds delay

If all attempts fail, the error is logged but does not affect the scan result.

### Security

- Only HTTPS webhook URLs are accepted (HTTP is rejected)
- Private IPs, loopback addresses, and link-local addresses are blocked (SSRF protection)
- HMAC signatures use timing-safe comparison (`hmac.compare_digest`)
- Webhook target responses are discarded (not trusted)

## Email / Slack Notifications

BrokenLinkBrief can send scan result notifications via **Email (SMTP)** and/or **Slack (Incoming Webhooks)**. Both channels are configured through environment variables and are automatically triggered after every `/scan` and `/scan-batch` call that finds broken links.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKENLINKBRIEF_SMTP_HOST` | — | SMTP server hostname (required for email) |
| `BROKENLINKBRIEF_SMTP_PORT` | `587` | SMTP port (465 = SSL, 587 = STARTTLS, 25 = plain) |
| `BROKENLINKBRIEF_SMTP_USER` | — | SMTP authentication username (required for email) |
| `BROKENLINKBRIEF_SMTP_PASSWORD` | — | SMTP authentication password (required for email) |
| `BROKENLINKBRIEF_SMTP_FROM` | — | Sender email address (required for email) |
| `BROKENLINKBRIEF_SLACK_WEBHOOK_URL` | — | Slack Incoming Webhook URL (required for Slack) |
| `BROKENLINKBRIEF_NOTIFY_ON` | `critical,warning,info` | Comma-separated severity levels that trigger notifications |
| `BROKENLINKBRIEF_NOTIFY_RATE_LIMIT` | `10` | Max notifications per rate interval per scanned URL |
| `BROKENLINKBRIEF_NOTIFY_RATE_INTERVAL` | `60` | Rate limit window in seconds |

### Email Notification Setup

1. Set SMTP environment variables for your email provider.

   **Gmail (App Password):**
   ```bash
   export BROKENLINKBRIEF_SMTP_HOST=smtp.gmail.com
   export BROKENLINKBRIEF_SMTP_PORT=587
   export BROKENLINKBRIEF_SMTP_USER=your@gmail.com
   export BROKENLINKBRIEF_SMTP_PASSWORD=your-app-password
   export BROKENLINKBRIEF_SMTP_FROM=your@gmail.com
   ```

   **SendGrid:**
   ```bash
   export BROKENLINKBRIEF_SMTP_HOST=smtp.sendgrid.net
   export BROKENLINKBRIEF_SMTP_PORT=587
   export BROKENLINKBRIEF_SMTP_USER=apikey
   export BROKENLINKBRIEF_SMTP_PASSWORD=SG.your-api-key
   export BROKENLINKBRIEF_SMTP_FROM=alerts@yourdomain.com
   ```

2. Start the server — notifications are sent automatically when broken links are found.

3. Email recipients are set to the same address as `BROKENLINKBRIEF_SMTP_FROM` (monitoring best practice). The subject line is formatted as `BrokenLinkBrief Report: <scanned_url>`.

### Slack Webhook Setup

1. Create a Slack Incoming Webhook:
   - Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → Incoming Webhooks
   - Activate the webhook and copy the URL
   - The URL looks like: `https://hooks.slack.com/services/T00/B00/xxxxx`

2. Set the environment variable:
   ```bash
   export BROKENLINKBRIEF_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/xxxxx
   ```

3. Start the server — Slack messages are posted automatically when broken links are found.

### Notification Templates & Severity Levels

Severity is automatically assigned based on HTTP status codes:

| Status Range | Severity | Emoji  |
|--------------|----------|--------|
| 5xx          | critical | 🔴     |
| 4xx          | warning  | 🟡     |
| 3xx / 2xx    | info     | 🟢     |

The notification includes:

- URL scanned and timestamp
- Total links checked
- Broken links grouped by severity with details (URL, status code, reason)

Control which severities trigger notifications with `BROKENLINKBRIEF_NOTIFY_ON`:

```bash
# Only critical errors
export BROKENLINKBRIEF_NOTIFY_ON=critical

# Critical and warnings (no info)
export BROKENLINKBRIEF_NOTIFY_ON=critical,warning
```

### Rate Limiting

Notifications use a token-bucket rate limiter per scanned URL to prevent flooding.

- **Default**: 10 notifications per 60 seconds per URL
- Configure via `BROKENLINKBRIEF_NOTIFY_RATE_LIMIT` (burst capacity) and `BROKENLINKBRIEF_NOTIFY_RATE_INTERVAL` (window in seconds)
- When the rate limit is hit, all channels are silently skipped for that URL until tokens refill

### Quick Start with Notifications

```bash
# Start the server with email and Slack configured
export BROKENLINKBRIEF_SMTP_HOST=smtp.gmail.com
export BROKENLINKBRIEF_SMTP_PORT=587
export BROKENLINKBRIEF_SMTP_USER=monitor@gmail.com
export BROKENLINKBRIEF_SMTP_PASSWORD=your-app-password
export BROKENLINKBRIEF_SMTP_FROM=monitor@gmail.com
export BROKENLINKBRIEF_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/xxxxx

python -m brokenlinkbrief.app

# In another terminal: scan a page — notifications fire automatically
curl "http://127.0.0.1:8000/scan?url=https://example.com"
```

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

The app reads the `PORT` environment variable automatically.

### Docker

```bash
docker build -t brokenlinkbrief .
docker run -p 8000:8000 brokenlinkbrief
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
```

## License

MIT
