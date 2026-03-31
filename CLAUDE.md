# 0x59 — Developer Guide

## What This Is

Lightweight CLI tool for inter-agent communication between Claude Code instances on a single host. Two agents discuss a topic via turn-based conversation stored in SQLite. Zero runtime dependencies.

## Critical Rules

1. **Zero runtime dependencies.** Only Python stdlib. No exceptions. Dev dependencies (`pytest`, `ruff`, `mypy`) are fine.
2. **All SQL lives in `db.py`.** No raw SQL anywhere else. If you need a query, add a method to `DB`.
3. **`ClaudeRunner` is the testability seam.** Never import `subprocess` in `coordinator.py`. Inject the runner. Tests use `FakeClaude`.
4. **WAL mode is non-negotiable.** Always enable at connection open. Observers depend on it.
5. **Fail fast with context.** Never silently swallow errors. Subprocess failures, JSON parse errors, DB errors — surface them all.

## Package Naming

- CLI command: `0x59`
- Python package: `zx59` (Python identifiers can't start with digits)
- PyPI name: `zx59`

## Development

```bash
uv sync                              # install dependencies
uv run pytest                        # run tests
uv run pytest --cov --cov-report=term # with coverage
uv run ruff check src tests          # lint
uv run ruff format src tests         # format
uv run mypy src                      # type check
```

## Architecture

```
Human CLI → Coordinator → claude -p (Agent A) ↔ SQLite ↔ claude -p (Agent B)
```

- **Turn-based**: Agent A speaks, then B, sequentially. No async.
- **SQLite is the bus**: storage, coordination, history, artifacts — one file.
- **No daemon**: coordinator runs on demand, agents invoked via `claude -p` and exit after each turn.

## Test-First

Write the failing test before the implementation. Use `FakeClaude` for coordinator tests. Target 80% coverage minimum.

## Conventions

- `ruff` for lint + format (line length 100, Python 3.10 target)
- `mypy --strict` for type checking
- `hatchling` build backend, `uv` package manager
- Commit messages explain "why", not "what"
- No TODOs without issue numbers

## Verification

| Task type | Done when |
|-----------|-----------|
| Bug fix | Test reproducing the bug + full suite green + lint + types |
| New feature | New tests + coverage ≥80% + full suite green + lint + types |
| Refactor | All existing tests pass + lint + types |

```bash
uv run pytest && uv run ruff check src tests && uv run mypy src
```

## Compact Instructions

When compressing, preserve in priority order:

1. Critical Rules 1–5 (NEVER summarize)
2. Architecture diagram and constraints
3. Modified files and verification status
4. Open TODOs and rollback notes

## Gotchas

### AppleScript String Escaping (notify.py)

`osascript -e 'display notification "..."'` does not support `\n` escape sequences. A literal newline inside the string is a syntax error that silently fails (caught by the `try/except`). Always sanitize: replace `\n` with space, strip `\r`, escape `\` and `"`. This affects every real invocation since LLM output is almost always multi-line.

### Python `write_text` Encoding

`Path.write_text(content)` uses `locale.getpreferredencoding()`, not UTF-8. Since SQLite stores TEXT as UTF-8, always pass `encoding="utf-8"` explicitly to avoid corruption on non-UTF-8 locales.

### Shared Exceptions Live in `errors.py`

`ClaudeError` and `ClaudeResponseError` are in `errors.py`, not `runner.py`. This keeps `coordinator.py` decoupled from the subprocess module. `runner.py` re-exports both for backwards compatibility.
