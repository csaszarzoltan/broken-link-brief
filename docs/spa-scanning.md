# SPA Scanning Guide

BrokenLinkBrief can scan pages that rely on client-side JavaScript to render links — single-page applications (SPAs), React/Vue/Angular apps, and any page where navigation elements are created dynamically.

## Prerequisites

### Install Playwright

```bash
pip install -e ".[playwright]"
playwright install chromium
```

This installs the `playwright` Python package and downloads the Chromium browser binary (~300 MB).

### Verify Installation

```python
from brokenlinkbrief.spa_scanner import SpaScanner

scanner = SpaScanner()
print("SPA scanner ready")
```

If Playwright is not installed, calling `scan_page(url, render_js=True)` raises `NotImplementedError` with installation instructions.

## Usage

### HTTP API

Add `render_js=true` to any `/scan` request:

```bash
# Standard scan (raw HTML extraction)
curl "http://127.0.0.1:8000/scan?url=https://example.com"

# SPA scan (renders JavaScript first)
curl "http://127.0.0.1:8000/scan?url=https://your-spa.com&render_js=true"

# SPA scan with export format
curl "http://127.0.0.1:8000/scan?url=https://your-spa.com&render_js=true&format=csv"
```

### Programmatic API

```python
from brokenlinkbrief.spa_scanner import SpaScanner

scanner = SpaScanner(headless=True)

# Render JavaScript and extract links
results = scanner.scan_page("https://your-spa.com", render_js=True)

for link in results:
    print(f"{link.url} → status={link.status}, reason={link.reason}")
```

### Raw HTML Extraction (No Playwright)

```python
from brokenlinkbrief.spa_scanner import SpaScanner

scanner = SpaScanner()

# Skip JavaScript rendering — regex-based extraction only
results = scanner.scan_page("https://example.com", render_js=False)
```

### Extract Links from Rendered HTML

If you already have rendered HTML (e.g., from your own Playwright session):

```python
from brokenlinkbrief.spa_scanner import SpaScanner

scanner = SpaScanner()
absolute_urls = scanner.render_and_extract_links(rendered_html, base_url)
```

## How It Works

1. **Launch**: Playwright starts a headless Chromium browser instance
2. **Navigate**: The target URL is loaded with `wait_until="networkidle"` (30-second timeout)
3. **Extract**: The fully rendered DOM is scanned for `<a href="...">` tags
4. **Resolve**: Relative URLs are resolved against the base URL
5. **Deduplicate**: Results are merged without duplicates

The scanner uses `contextlib.suppress(Exception)` around page navigation so that partial renders (e.g., pages with failed subresources) still produce link results.

## When to Use SPA Scanning

| Scenario | `render_js` | Reason |
|----------|-------------|--------|
| Static HTML pages | `false` (default) | No JavaScript rendering needed |
| Server-rendered `<a>` tags | `false` (default) | Links already in raw HTML |
| React/Vue/Angular apps | `true` | Links created by JavaScript |
| `document.createElement('a')` | `true` | Dynamic link creation |
| JavaScript-injected navigation | `true` | No server-side HTML |
| Intranet pages with auth | depends | Playwright may not have session cookies |

## Limitations

- **Disk**: Chromium binary requires ~300 MB
- **Speed**: JavaScript rendering adds 2–10 seconds per page
- **Auth**: Pages behind login walls or CAPTCHAs may not render correctly
- **Resources**: Each scan uses a Chromium process (CPU + memory)
- **Failure mode**: Playwright errors return a single `playwright-error` result — the scan does not crash

## Configuration

### Headless Mode

```python
# Default: headless (no visible browser window)
scanner = SpaScanner(headless=True)

# Visible browser (for debugging)
scanner = SpaScanner(headless=False)
```

### Environment Variables

SPA scanning uses the same environment variables as the rest of BrokenLinkBrief. No additional configuration is required.

## Integration with Link Diff

SPA scan results are stored with `scan_mode="spa"` in the link state database. This allows the diff engine to track whether a link was discovered via static HTML extraction or JavaScript rendering:

```python
from brokenlinkbrief.link_state import LinkStateStore

store = LinkStateStore(db_connection)

# Upsert with SPA scan mode
store.upsert_links(project_id, target_url, links, scan_mode="spa")
```

## Troubleshooting

### "Playwright is required for JS rendering"

Playwright is not installed. Run:

```bash
pip install -e ".[playwright]"
playwright install chromium
```

### Chromium binary not found

Reinstall the browser:

```bash
playwright install chromium
```

### Scan returns `playwright-error`

Playwright failed to launch or navigate. Common causes:
- Chromium binary missing or corrupted
- Insufficient memory (Chromium needs ~200 MB RAM)
- Network timeout (page took >30 seconds to reach `networkidle`)

The scanner returns a single `LinkResult` with `reason="playwright-error"` so the scan can continue without crashing.
