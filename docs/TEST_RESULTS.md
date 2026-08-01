# BrokenLinkBrief 1.1.1 Validation Results

Validated on 2026-08-01 in the handoff environment.

## Baselines

Before the saved-project work:

```text
331 passed, 1 xpassed in 24.77s
```

After version 1.1.0:

```text
339 passed, 1 xpassed in 23.93s
```

## 1.1.1 TDD evidence

Six failing-first tests were added for project update, archived listing, restore, PUT API behavior, restore API behavior, and dashboard lifecycle actions. The first execution reported six failures. Implementation then proceeded incrementally. During targeted regression, one restore-route placement defect remained and produced a 404; the route was moved to the POST handler and all focused tests passed.

Focused result:

```text
15 passed in 1.11s
```

## Final automated regression

```text
345 passed, 1 xpassed in 24.73s
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
