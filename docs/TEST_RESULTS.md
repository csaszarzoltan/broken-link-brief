# BrokenLinkBrief 1.1.4 Validation Results

Validated on 2026-08-01 in the handoff environment.

## Release progression

- Original 1.0.7 baseline: `331 passed, 1 xpassed`
- Saved projects 1.1.0: `339 passed, 1 xpassed`
- Project lifecycle 1.1.1: `345 passed, 1 xpassed`
- Project quick scan 1.1.2: `349 passed, 1 xpassed`
- Project portability 1.1.3: `355 passed, 1 xpassed`

## 1.1.4 TDD evidence

Five failing-first tests were added for project-copy identity, deterministic copy naming, duplicate API behavior, missing-source handling, and the dashboard Duplicate action. The initial run reported five failures because duplication did not exist.

Focused result after implementation:

```text
30 passed in 2.56s
```

The focused suite covered project creation, editing, archive/restore, quick scanning, summaries, import/export, duplication, API behavior, SSRF validation, dashboard contracts, and embedded JavaScript syntax.

## Final automated regression

```text
360 passed, 1 xpassed in 26.59s
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
