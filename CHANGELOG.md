# Changelog

## v0.7.0 (2026-07-22)

### Features
- **Batch scanning** — POST /scan-batch endpoint accepts up to 50 URLs in a single request for parallel link checking
- **Concurrency control** — configurable worker count (max 20) for parallel URL scanning
- **Duplicate URL rejection** — returns HTTP 400 when duplicate URLs are present in a batch request
- **SSRF protection** — per-URL SSRF validation applied to all URLs in the batch
- **Batch JSONL logging** — batch scan results logged with batch_id and latency for traceability

### Tests
- Added 39 new tests across 2 test files (test_batch_endpoint.py: 10/10, test_batch_scan.py: 29/29)
- Total test count: 170 (up from 130)

## v0.6.0 (2026-07-21)

### Features
- **Webhook notifications** — register HTTPS webhook URLs to receive scan results when broken links are detected
- **HMAC-SHA256 signing** — all webhook payloads are signed with an optional secret; verification uses timing-safe comparison
- **Retry with exponential backoff** — failed webhook deliveries retry up to 3 times (1s, 2s, 4s delays)
- **SSRF protection for webhook URLs** — blocks private IPs, loopback addresses, and non-HTTPS schemes
- **POST /webhooks endpoint** — register, list, and remove webhook URLs via HTTP API with token authentication
- **Duplicate URL detection** — returns HTTP 409 when registering an already-registered URL

### Tests
- Added 90 new tests across 3 test files (test_webhook.py, test_webhook_registration.py, test_webhook_ssrf.py)
- Total test count: 130 (up from 41)

### Docs
- Updated README with webhook notification features and API documentation

## v0.5.0 (2026-07-20)

### Features
- Initial release — broken link scanner with JSON/CSV/Markdown/JSONL export
- Token-based authentication
- SSRF protection for scan targets
- Railway deployment support
- JSONL usage logging
