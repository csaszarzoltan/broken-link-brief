# BrokenLinkBrief 1.1.2 Validation Results

Validated on 2026-08-01 in the handoff environment.

## Release progression

- Original 1.0.7 baseline: `331 passed, 1 xpassed`
- Saved projects 1.1.0: `339 passed, 1 xpassed`
- Project lifecycle 1.1.1: `345 passed, 1 xpassed`

## 1.1.2 TDD evidence

Four failing-first tests were added for latest target-snapshot aggregation, unscanned-project summaries, project API summary output, and one-action project scanning. The initial run reported four failures because summary and quick-scan behavior did not exist.

Focused result after implementation:

```text
19 passed in 1.84s
```

This focused suite covered project creation, editing, archive/restore, latest-state summaries, quick scanning, API behavior, dashboard contracts, and embedded JavaScript syntax.

## Final automated regression

```text
349 passed, 1 xpassed in 25.24s
```

Command:

```bash
python -m pytest -q --disable-warnings
```

No test failed. The XPASS is a pre-existing expected-failure test whose behavior is implemented.

## Additional validation

- Python source and tests passed `python -m compileall -q src tests`.
- Embedded dashboard JavaScript passed `node --check`.
- ZIP integrity validation reported no compressed-data errors.
- Runtime databases, history, caches, bytecode, and temporary files were excluded.

## Tooling limitation

Ruff is declared in the development dependencies, but its executable was unavailable in the handoff environment. Install development dependencies and run `ruff check src tests` before production release.
