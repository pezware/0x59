# Development Guide

## Setup

```bash
git clone https://github.com/pezware/0x59.git
cd 0x59
uv sync          # install all dependencies (dev included)
```

Run the tool locally:

```bash
uv run 0x59 --help
```

## Code structure

```
src/zx59/
  cli.py           argparse entry point, subcommand dispatch
  coordinator.py   turn engine — runs the agent conversation loop
  db.py            all SQLite operations (queries, migrations, WAL setup)
  runner.py        subprocess wrapper for calling `claude -p`
  context.py       message windowing for long conversations
  prompt.py        assembles the prompt sent to each agent per turn
  schema.py        JSON schema for structured agent responses
  export.py        artifact export to files
  notify.py        desktop notifications (macOS/Linux)
  __init__.py      version string

tests/
  conftest.py      FakeClaude test double, shared fixtures
  test_*.py        one test file per module
```

## Architecture

```
CLI (argparse)
  |
  v
Coordinator         turn engine — the core loop
  |
  +-- ClaudeRunner  protocol interface (injected)
  |     |
  |     +-- SubprocessClaudeRunner (real: calls `claude -p`)
  |     +-- FakeClaude             (tests: returns canned responses)
  |
  +-- DB            all database access
  |
  +-- build_prompt  assembles prompt per turn
  +-- window_messages  trims history for token budget
```

Key design decisions:

- **Turn-based, not async.** Agent A speaks, then B, sequentially. The protocol is fundamentally sequential — async would add complexity without benefit.
- **SQLite is the bus.** One file handles storage, coordination, history, and artifacts. WAL mode allows concurrent readers (for future observer support).
- **No daemon.** The coordinator runs on demand, calls `claude -p` per turn, and exits.
- **Zero runtime dependencies.** Only Python stdlib. Dev dependencies (pytest, ruff, mypy) are fine.

### The ClaudeRunner seam

The most important architectural choice. `ClaudeRunner` is a Python Protocol:

```python
class ClaudeRunner(Protocol):
    def run(self, prompt: str, model: str, json_schema: str) -> str: ...
```

The real implementation (`SubprocessClaudeRunner`) calls `claude -p` via subprocess. Tests inject `FakeClaude` which returns pre-configured responses. This means:

- No subprocess mocking in tests
- No network calls in tests
- Coordinator tests are fast and deterministic

### Database rules

All SQL lives in `db.py`. No raw SQL anywhere else. If you need a new query, add a method to the `DB` class. WAL mode is enabled at every connection open — observers and future concurrent readers depend on it.

### Decision protocol

Both agents must set `decision_reached: true` in consecutive turns. One agent cannot unilaterally declare consensus. The coordinator tracks a `pending_decision` flag that resets if the second agent disagrees.

## Running tests

```bash
uv run pytest                          # all tests
uv run pytest tests/test_db.py -v      # single module
uv run pytest --cov --cov-report=term  # with coverage report
```

Coverage minimum: **80%**, enforced in CI.

### Writing tests

- Test behavior, not implementation
- One assertion per test
- Use `FakeClaude` for coordinator tests — never mock subprocess
- Use the `db` fixture from `conftest.py` for database tests (creates a temp DB)
- Use `make_response()` and `setup_channel()` helpers from conftest

Example:

```python
from tests.conftest import FakeClaude, make_response, setup_channel

def test_decision_requires_both_agents(db):
    channel_id = setup_channel(db)
    runner = FakeClaude([
        make_response("I propose X", decision=True, summary="Use X"),
        make_response("Agreed", decision=True, summary="Use X"),
    ])
    coord = Coordinator(db, runner)
    result = coord.run(channel_id)
    assert result.status == "decided"
```

## Linting, formatting, type checking

```bash
uv run ruff check src tests          # lint
uv run ruff format src tests         # format
uv run mypy src                      # type check (strict mode)
```

Configuration lives in `pyproject.toml`:

- **ruff**: line length 100, Python 3.10 target, select rules: E, F, I, UP, B, SIM, RUF, PTH, C4
- **mypy**: strict mode, warn_return_any
- **pytest**: short tracebacks, quiet output

## uv and Python best practices

This project follows modern Python packaging conventions. Here's what to know.

### uv as the package manager

uv replaces pip, pip-tools, virtualenv, and pyenv in one tool. Key commands:

```bash
uv sync                    # install all deps (reads uv.lock)
uv run <command>           # run in the project's venv
uv add <package>           # add a runtime dependency
uv add --dev <package>     # add a dev dependency
uv build                   # build sdist + wheel
uv lock --upgrade          # refresh the lock file
```

### Lock file (`uv.lock`)

The lock file pins exact versions of all dependencies and is checked into git. `uv sync` always installs from the lock file, ensuring reproducible builds across machines and CI. Never edit it by hand — use `uv lock` to regenerate.

### `exclude-newer` (supply chain security)

`pyproject.toml` sets an `exclude-newer` date that prevents uv from resolving packages published after that timestamp. This defends against supply-chain attacks where a compromised package version is uploaded after your lock file was last generated. Update it deliberately when upgrading dependencies:

```toml
[tool.uv]
exclude-newer = "2026-03-29T00:00:00Z"
```

### `.python-version`

Pins the development Python version so `uv sync` and `uv run` use a consistent interpreter across all machines. Set to the version used in CI's primary test job.

### `py.typed` marker (PEP 561)

The empty file `src/zx59/py.typed` signals to tools like mypy that this package ships inline type annotations. Without it, downstream consumers running mypy will silently treat the package as untyped.

### src layout

The `src/zx59/` layout prevents accidental imports of the source directory during testing. A flat layout can silently import the local directory instead of the installed package — the src layout makes this impossible.

### Dependency groups

Dev-only tools (pytest, ruff, mypy, pre-commit) live in `[dependency-groups]` in `pyproject.toml`, not in `[project.dependencies]`. This keeps the runtime dependency list empty (zero dependencies) while still providing a reproducible dev environment.

### Pre-commit hooks

Configured in `.pre-commit-config.yaml`. Runs automatically on `git commit`:

- `ruff --fix` — lint with auto-fix
- `ruff-format` — code formatting
- `trailing-whitespace`, `end-of-file-fixer` — file hygiene
- `check-yaml`, `check-toml` — config file validation
- `check-merge-conflict` — prevents committing merge markers

Install hooks after cloning:

```bash
uv run pre-commit install
```

## Package naming

The CLI command is `0x59` but Python identifiers can't start with a digit, so:

| Context | Name |
|---|---|
| CLI command | `0x59` |
| Python package | `zx59` |
| PyPI name | `zx59` |
| Import | `import zx59` |

## Building and publishing

Build:

```bash
uv build    # creates sdist + wheel in dist/
```

The project uses `hatchling` as the build backend. All configuration is in `pyproject.toml` — no `setup.py`, no `setup.cfg`.

### Release process

1. Update version in `pyproject.toml` and `src/zx59/__init__.py`
2. Commit: `git commit -m "release: vX.Y.Z"`
3. Tag: `git tag vX.Y.Z`
4. Push: `git push && git push --tags`

CI handles the rest — the release workflow builds, tests, and publishes to PyPI automatically using OIDC trusted publishing.

### CI pipelines

- **ci.yml**: runs on push to `main` and all PRs — lint, format check, mypy, pytest across Python 3.10-3.13
- **release.yml**: runs on `v*` tags — builds and publishes to PyPI, creates GitHub Release

## Conventions

- Commit messages explain "why", not "what"
- No TODOs without issue numbers
- Pre-commit hooks run ruff check + format automatically
- All new functionality needs tests
- Every commit must compile and pass all tests
