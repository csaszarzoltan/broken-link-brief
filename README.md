# BrokenLinkBrief

A compact stdlib-based service that scans a page for links, checks their HTTP status, and exports a shareable brief (JSON, CSV, markdown, or JSONL).

## Features

- 🔍 Scan any webpage for broken links
- 📊 Export as JSON, CSV, Markdown, or JSONL
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
| POST | `/webhooks` | Required | Register a webhook URL |
| GET | `/webhooks` | Required | List registered webhooks |
| DELETE | `/webhooks/<id>` | Required | Remove a webhook |

## Authentication

Set `BROKENLINKBRIEF_SCAN_TOKEN` to require a matching token on `/scan` and `/webhooks`.

## Webhook Notifications

Register an HTTPS webhook URL to receive notifications when broken links are detected during scans.

### Register a Webhook

```bash
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
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
