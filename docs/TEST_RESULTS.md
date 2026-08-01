# BrokenLinkBrief 1.1.5 Validation Results

Validated on 2026-08-01 in the handoff environment.

## Release progression

- Original 1.0.7 baseline: `331 passed, 1 xpassed`
- Saved projects 1.1.0: `339 passed, 1 xpassed`
- Project lifecycle 1.1.1: `345 passed, 1 xpassed`
- Project quick scan 1.1.2: `349 passed, 1 xpassed`
- Project portability 1.1.3: `355 passed, 1 xpassed`
- Project duplication 1.1.4: `360 passed, 1 xpassed`

## 1.1.5 TDD evidence

Five failing-first tests were added for pin persistence and ordering, automatic migration of an existing 1.1 database, unpinned duplication, pin API behavior, and dashboard pin controls. The initial run reported five failures because pinning did not exist.

Focused result after implementation:

```text
35 passed in 2.45s
```

The focused suite covered project creation, lifecycle, quick scanning, summaries, portability, duplication, pinning, database migration, API behavior, dashboard contracts, and embedded JavaScript syntax.

## Final automated regression

```text
365 passed, 1 xpassed in 25.96s
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
