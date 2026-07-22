# BrokenLinkBrief

A compact stdlib-based service that scans a page for links, checks their HTTP status, and exports a shareable brief (JSON, CSV, markdown, or JSONL).

## Features

- 🔍 Scan any webpage for broken links
- 📊 Export as JSON, CSV, Markdown, or JSONL
- ⚡ Batch scanning — check up to 50 URLs in parallel in a single request
- 🔔 Webhook notifications when broken links are found
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
