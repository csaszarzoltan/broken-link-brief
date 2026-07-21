# BrokenLinkBrief Micro-Feature

## Goal
Add the smallest shippable BrokenLinkBrief increment to the existing repo as a new local package/app module, keeping the existing `repo_productization_kit` helpers untouched.

## Context
- Repo path: /home/zoltan/micro-saas-lab
- Python layout: `src/repo_productization_kit/...`, tests under `tests/unit/...`
- Quality gate: `python3 -m ruff check src tests` and `python3 -m pytest -q` must both pass.
- Existing docs already mention `BrokenLinkBrief`; keep README/PHASE1-CANDIDATE parity, do not rewrite unrelated content.

## Scope
Add a tiny FastAPI app module for link scanning plus matching tests in the existing repo package layout. Hard rule: do not modify `src/repo_productization_kit/*`. Do not write or rewrite unrelated global docs if not needed. Minimal new files only.

## Acceptance Criteria
1. New module under `apps/brokenlinkbrief/package.py` exposes:
   - `LinkResult` model with at least `url: str`, `status: int | None`, `reason: str | None`, `location: str | None`
   - `scan_page(url: str, timeout: float = 10.0) -> list[LinkResult]`
   - `render_markdown(results: list[LinkResult]) -> str`
2. `scan_page` extracts href links from HTML, falls back to same-host absolute URL resolution when `href` is relative, and fetches each unique URL with HTTP HEAD first and GET fallback when HEAD is unsupported. Network failure stays as a result item with `status=None` and a concise `reason`; timeout defaults to 10.0s.
3. New endpoint under `apps/brokenlinkbrief/app.py`: `GET /scan?url=` returning JSON array with the exact shape `{url, status, reason, location}`. Add `GET /health` returning `{"status":"ok"}`.
4. New tests under `tests/unit/test_brokenlinkbrief.py` cover:
   - relative link resolution
   - successful status mapping
   - redirect handling represented via `location`
   - network failure remains in results with `status=None`
5. Docs parity:
   - Update README.md with a `## BrokenLinkBrief` section describing local run command, endpoint summary, and export behavior.
   - Keep docs/CONTINUOUS-DELIVERY.md unchanged.
6. Validation must pass locally:
   - `python3 -m ruff check src tests apps || true` must be clean or at least the new app files inspected.
   - All tests under `tests/unit/test_brokenlinkbrief.py` must pass.
7. Commit with message: `feat(brokenlinkbrief): add page link-scan API and markdown brief`, then create annotated git tag `v0.2.0` from the commit and push both.

## Constraints
- Use only stdlib + package dependencies already aligned with repo conventions (`packaging` is present; avoid adding new runtime dependencies).
- Keep behavior small and testable.
- Do not replace backend dependencies without an explicit success path.
