# 0x59 — Specification

> Lightweight inter-agent communication for Claude Code instances on a single host.

**Version**: 0.1.0 (draft)
**License**: MIT
**Status**: Pre-implementation

---

## 1. Problem Statement

Two or more Claude Code instances running on the same machine have no built-in way to hold a structured conversation. Current workarounds (shared files, copy-paste) are manual, lossy, and produce no auditable record.

**0x59** provides a minimal, CLI-first tool that lets Claude Code agents discuss a topic, reach a decision, and produce artifacts — all stored in a local SQLite database with zero external dependencies.

## 2. Design Principles

- **Zero runtime dependencies** — Python stdlib only (`sqlite3`, `subprocess`, `argparse`, `json`, `dataclasses`)
- **No daemon** — the coordinator runs on demand, agents are invoked via `claude -p` and exit after each turn
- **SQLite is the bus** — storage, coordination, history, and artifact management in one file
- **Turn-based** — Agent A speaks, then Agent B, sequentially. No async complexity for a fundamentally sequential protocol
- **CLI-first** — every operation is a single shell command
- **Cost-aware** — model selection per channel and per agent (`haiku` for quick chats, `sonnet`/`opus` for deep discussions)

## 3. Architecture

```
                     Human (CLI)
                         │
                         ▼
                  ┌──────────────┐
                  │  0x59 CLI     │   bash entry point
                  │  (argparse)   │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  Coordinator  │   turn engine (Python)
                  │               │   calls claude -p per turn
                  └──────┬───────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
     ┌────────────┐ ┌────────┐ ┌────────────┐
     │ claude -p   │ │ SQLite │ │ claude -p   │
     │ (Agent A)   │ │  .db   │ │ (Agent B)   │
     └────────────┘ └────────┘ └────────────┘
                         ▲
                         │ read-only (phase 2)
                    ┌────┴────┐
                    │Observer │
                    └─────────┘
```

### Component Inventory

| Component | File | Responsibility | Approx. Size |
|---|---|---|---|
| CLI | `src/zx59/cli.py` | Argument parsing, subcommand dispatch | ~60 lines |
| Coordinator | `src/zx59/coordinator.py` | Turn loop, decision detection, error handling | ~120 lines |
| Database | `src/zx59/db.py` | All SQLite operations, migrations, WAL setup | ~80 lines |
| Context | `src/zx59/context.py` | Message windowing for long conversations | ~40 lines |
| Prompt | `src/zx59/prompt.py` | Prompt assembly from messages + system prompt | ~30 lines |
| Schema | `src/zx59/schema.py` | JSON schema definitions for structured output | ~20 lines |
| Errors | `src/zx59/errors.py` | Shared exceptions (`ClaudeError`, `ClaudeResponseError`) | ~20 lines |
| Notify | `src/zx59/notify.py` | macOS/Linux desktop notifications | ~20 lines |
| Export | `src/zx59/export.py` | Artifact extraction to files | ~20 lines |
| **Total** | | | **~410 lines** |

### Package Naming

`0x59` is the CLI command name. `zx59` is the Python package name (Python identifiers cannot start with a digit). The mapping is:

```
CLI command:     0x59
PyPI package:    zx59
Import:          import zx59
Internal:        src/zx59/
```

## 4. SQLite Schema

Database location:
- macOS: `~/Library/Application Support/0x59/channels.db`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/0x59/channels.db`
- Override: `0x59 --db /path/to/file.db`

WAL mode is enabled at connection open. Foreign keys are enforced.

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- A conversation with purpose
CREATE TABLE channels (
    id          TEXT PRIMARY KEY,            -- short slug: "auth-design-a3f"
    topic       TEXT NOT NULL,              -- "Design the auth middleware"
    agenda      TEXT,                        -- "1. Token format\n2. Expiry policy"
    status      TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'decided', 'closed')),
    model       TEXT NOT NULL DEFAULT 'sonnet',
    max_turns   INTEGER NOT NULL DEFAULT 20,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at  TEXT,
    decision    TEXT
);

-- Who participates
CREATE TABLE participants (
    channel_id    TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL,             -- "architect", "reviewer"
    role          TEXT NOT NULL DEFAULT 'participant'
                  CHECK (role IN ('participant', 'observer')),
    system_prompt TEXT,                       -- per-agent role description
    model         TEXT,                       -- per-agent model override
    PRIMARY KEY (channel_id, agent_id)
);

-- Conversation messages
CREATE TABLE messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id     TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    sender         TEXT NOT NULL,             -- agent_id or "system"
    content        TEXT NOT NULL,
    msg_type       TEXT NOT NULL DEFAULT 'chat'
                   CHECK (msg_type IN ('chat', 'proposal', 'decision', 'summary', 'artifact')),
    token_estimate INTEGER,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Produced documents
CREATE TABLE artifacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    message_id   INTEGER REFERENCES messages(id),
    name         TEXT NOT NULL,               -- "auth-design.md"
    content      TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/markdown',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Schema Migrations

Handled via `PRAGMA user_version`. Each migration is a numbered function in `db.py`. No external migration tool.

```python
# Simplified migration pattern
MIGRATIONS = {
    0: _create_initial_schema,   # v0.1.0
    # 1: _add_cost_tracking,     # future
}
```

## 5. Conversation Protocol

### Turn Flow

```
1. Coordinator creates channel (topic, agenda, participants)
2. Coordinator inserts system message: seeding prompt with topic + agenda
3. Loop:
   a. Select next agent (round-robin for 2 agents)
   b. Build prompt:
      - Agent's system_prompt (role definition)
      - Conversation history (windowed if long)
      - Instruction: "Respond. Set decision_reached=true when consensus is reached."
   c. Call: claude -p --model <model> --json-schema <schema> "<prompt>"
   d. Parse structured JSON response
   e. INSERT message into SQLite
   f. If response.decision_reached == true → break
   g. If response contains artifacts → INSERT into artifacts table
   h. If turn_count >= max_turns → force final summary, break
4. UPDATE channel: status='decided', decision=summary
5. Notify human (terminal-notifier / osascript)
6. Exit
```

### Structured Response Schema

Each agent response is constrained by `--json-schema`:

```json
{
  "type": "object",
  "properties": {
    "message": {
      "type": "string",
      "description": "The agent's conversational response"
    },
    "decision_reached": {
      "type": "boolean",
      "description": "True when the agent believes consensus has been reached"
    },
    "decision_summary": {
      "type": "string",
      "description": "Summary of the decision (required when decision_reached=true)"
    },
    "artifacts": {
      "type": "array",
      "description": "Documents or code produced during this turn",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "content": { "type": "string" },
          "content_type": { "type": "string", "default": "text/markdown" }
        },
        "required": ["name", "content"]
      }
    }
  },
  "required": ["message", "decision_reached"]
}
```

### Decision Detection

A decision is reached when **both agents** set `decision_reached: true` in consecutive turns. This prevents one agent from unilaterally declaring consensus. The coordinator tracks this:

```
Agent A: decision_reached=true  → pending_decision=true
Agent B: decision_reached=true  → confirmed. Channel decided.
Agent B: decision_reached=false → pending_decision reset. Continue.
```

### Context Windowing

To keep token usage bounded in longer conversations, middle messages are dropped:

| Conversation Length | Strategy |
|---|---|
| 1-10 turns | Full history |
| 11-20 turns | First message + last 5 turns |
| 21+ turns | First message + last 3 turns |

Token estimation: `len(text) // 4` (naive but sufficient — this is for windowing, not billing).

Dropped messages are silently omitted (no summarization). A future enhancement could summarize dropped turns via a `claude -p --model haiku` call, stored as `msg_type='summary'`. This would improve agent context at the cost of an extra API call per windowed turn.

## 6. CLI Interface

Entry point: `0x59` (via `[project.scripts]` in pyproject.toml).

### Commands

```
0x59 chat <topic>                      Start a quick 2-agent chat
0x59 discuss <topic> [options]         Start a formal discussion with roles
0x59 log <channel-id>                  Print full transcript
0x59 decision <channel-id>             Print the decision summary
0x59 artifacts <channel-id>            List artifacts from a channel
0x59 export <channel-id> [file] [--name NAME]  Export artifact to file
0x59 ls [--open|--decided|--closed]    List channels
```

### Options for `discuss`

```
--agent <id> <system-prompt>    Define an agent with role (repeatable)
--model <model>                 Default model for all agents (default: sonnet)
--max-turns <n>                 Maximum turns before forced summary (default: 20)
--agenda <text>                 Structured agenda items
--notify                        Send desktop notification on decision (default: true)
--db <path>                     Override database path
```

### Examples

```bash
# Quick chat — minimal arguments, uses default agent roles
0x59 chat "Should we use JWT or session cookies?"

# Formal discussion with specific roles
0x59 discuss "Auth middleware design" \
  --agent architect "Pragmatic backend architect. Favor simplicity and performance." \
  --agent reviewer "Security-focused reviewer. Challenge assumptions, find edge cases." \
  --agenda "1. Token storage format
2. Session expiry policy
3. Refresh token strategy" \
  --model sonnet \
  --max-turns 15

# After decision, export the produced document
0x59 export auth-middleware-a3f ./decisions/auth-design.md

# List all discussions
0x59 ls --decided
```

### Default Agent Roles

When no `--agent` flags are provided (e.g., `0x59 chat`), two default agents are used:

- **proposer**: "You are a thoughtful technical contributor. Propose solutions, consider trade-offs, and be willing to reach consensus."
- **challenger**: "You are a critical reviewer. Stress-test proposals, identify risks, and push for clarity. Agree only when genuinely convinced."

## 7. Notification

On decision reached:

```bash
# macOS (primary)
osascript -e 'display notification "Auth middleware: Use JWT with refresh tokens" with title "0x59 — Decision" sound name "Glass"'

# macOS (if terminal-notifier is installed)
terminal-notifier -title "0x59" -subtitle "Decision reached" \
  -message "Auth middleware: Use JWT with refresh tokens" -sound Glass

# Linux (future)
notify-send "0x59 — Decision" "Auth middleware: Use JWT with refresh tokens"
```

Notification failure is non-fatal — wrapped in try/except, logged to stderr.

Notification text is sanitized before sending:
- **macOS**: Backslashes and double quotes are escaped. Newlines are replaced with spaces (AppleScript string literals don't support `\n` escape sequences — a literal newline breaks the string). Carriage returns are stripped.
- **Linux**: HTML/Pango markup is escaped via `html.escape()` to prevent `notify-send` from rendering unintended formatting.

## 8. Error Handling

### Claude CLI Errors

| Scenario | Handling |
|---|---|
| `claude -p` returns non-zero exit | Raise `ClaudeError(returncode, stderr)` (from `errors.py`). Coordinator logs and aborts. |
| Response is not valid JSON | Raise `ClaudeResponseError(raw_output)` (from `errors.py`). Log raw output for debugging. |
| `claude -p` hangs | `subprocess.run(timeout=300)`. On timeout, kill and raise. |
| `claude` not found in PATH | Fail fast at startup with clear message: "Claude Code CLI required." |

### Database Errors

- Schema migration failure: abort with message, don't corrupt existing data
- Disk full: SQLite raises `OperationalError`, surfaced to user
- Concurrent write conflict: WAL mode prevents this in normal operation

### General Principle

Fail fast with context. Never silently swallow. The coordinator surfaces all errors to the CLI layer, which formats them for the human.

## 9. Project Structure

```
0x59/
├── .github/
│   └── workflows/
│       ├── ci.yml              # lint + test on push/PR
│       └── release.yml         # build + PyPI + GitHub Release on tag
├── src/
│   └── zx59/
│       ├── __init__.py         # __version__ = "0.1.0"
│       ├── cli.py              # argparse entry point
│       ├── coordinator.py      # turn engine + ClaudeRunner protocol
│       ├── db.py               # SQLite operations + migrations
│       ├── errors.py           # shared exceptions (ClaudeError, ClaudeResponseError)
│       ├── context.py          # message windowing
│       ├── prompt.py           # prompt assembly
│       ├── schema.py           # JSON schema definitions
│       ├── notify.py           # desktop notifications
│       └── export.py           # artifact export
├── tests/
│   ├── conftest.py             # FakeClaude, db fixture
│   ├── test_db.py
│   ├── test_context.py
│   ├── test_prompt.py
│   ├── test_coordinator.py
│   └── test_cli.py
├── docs/
│   ├── specs.md                # this document
│   └── contributing.md         # dev setup, PR process
├── README.md
├── LICENSE                     # MIT
├── pyproject.toml              # single config file (build, deps, tools)
└── .gitignore
```

### Why src layout?

Prevents accidental imports of the package from the project root during testing. A flat layout (`0x59/zx59/`) can silently import the source directory instead of the installed package — the src layout makes this impossible.

## 10. Tooling & Configuration

### pyproject.toml (single source of truth)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "zx59"
version = "0.1.0"
description = "Lightweight inter-agent communication for Claude Code instances"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
dependencies = []
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries",
]

[project.scripts]
"0x59" = "zx59.cli:main"

[project.urls]
Homepage = "https://github.com/pezware/0x59"
Repository = "https://github.com/pezware/0x59"
Issues = "https://github.com/pezware/0x59/issues"

[tool.hatchling.build]
packages = ["src/zx59"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.10",
    "pre-commit>=3.7",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--tb=short -q"

[tool.coverage.run]
source = ["src/zx59"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
```

### Package Manager: uv

- `uv sync` — install all dependencies (dev included)
- `uv run pytest` — run tests
- `uv run ruff check src tests` — lint
- `uv run mypy src` — type check
- `uv build` — build sdist + wheel
- `uvx zx59` — run without installing (end-user UX)

### Linting & Formatting: ruff

Single tool replaces black + isort + flake8 + pylint. Fast enough for pre-commit hooks.

### Type Checking: mypy (strict mode)

Runs in CI only — too slow for pre-commit on every save. Strict mode enforced.

### Pre-commit Hooks

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
```

## 11. Testing Strategy

### Framework

`pytest` only. No `unittest`, no async.

### The Critical Seam: ClaudeRunner Protocol

```python
from typing import Protocol

class ClaudeRunner(Protocol):
    def run(self, prompt: str, model: str, json_schema: dict | None = None) -> str: ...
```

The real implementation calls `subprocess.run(["claude", "-p", ...])`. Tests inject `FakeClaude`:

```python
class FakeClaude:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    def run(self, prompt: str, model: str, json_schema: dict | None = None) -> str:
        return next(self._responses)
```

This is the single most important testability decision. No `subprocess` mocking, no network mocking — just swap the runner.

### Test Matrix

| Module | What to Test | What NOT to Test |
|---|---|---|
| `test_db.py` | Schema creation, CRUD, WAL mode active, FK enforcement, migration idempotency | SQLite internals |
| `test_context.py` | Windowing truncation, empty input, oversized single message preserved | Token estimation accuracy |
| `test_prompt.py` | System prompt placement, message ordering, agent name injection | Prompt quality |
| `test_coordinator.py` | Turn count, stops on decision, persists messages, handles errors | Actual Claude responses |
| `test_cli.py` | `--help` exits 0, invalid subcommand exits nonzero, argument parsing | Desktop notifications |

### Coverage

Target: **80% minimum**, enforced by `pytest-cov` in CI.

### Test Execution

```bash
uv run pytest                          # all tests
uv run pytest tests/test_db.py -v      # single module
uv run pytest --cov --cov-report=term  # with coverage
```

## 12. CI/CD Pipelines

### CI — `.github/workflows/ci.yml`

Triggers: push to `main`, all pull requests.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check src tests
      - run: uv run ruff format --check src tests
      - run: uv run mypy src

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync
      - run: uv run pytest --cov=zx59 --cov-report=xml
      - uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.12'
        with:
          file: coverage.xml

  test-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run pytest
```

### Release — `.github/workflows/release.yml`

Triggers: push of `v*` tags.

```yaml
name: Release

on:
  push:
    tags: ["v*"]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true
```

### Distribution Channels

| Channel | Command | Notes |
|---|---|---|
| PyPI (uv) | `uvx zx59` | Zero-install run |
| PyPI (pip) | `pip install zx59` | Traditional install |
| PyPI (pipx) | `pipx install zx59` | Isolated install |
| GitHub Release | Download from Releases page | Manual install |

PyPI publishing uses **OIDC trusted publishing** — no API token needed in repository secrets.

### Version Management

Single source of truth: `version = "0.1.0"` in `pyproject.toml`.

Release process:
1. Update version in `pyproject.toml` and `src/zx59/__init__.py`
2. Commit: `git commit -m "release: v0.1.0"`
3. Tag: `git tag v0.1.0`
4. Push: `git push && git push --tags`
5. CI builds, tests, publishes automatically

## 13. Extensibility Roadmap

### Phase 1 — Core (v0.1.0)

- 2-agent and multi-agent turn-based discussion
- SQLite storage with full schema
- CLI: `chat`, `discuss`, `log`, `decision`, `artifacts`, `export`, `ls`
- Decision detection (mutual agreement between different agents)
- macOS/Linux notification on decision
- Context windowing for long conversations

### Phase 2 — Observer & Utilities (v0.2.0)

- `0x59 watch <channel>` — live tail a conversation in real-time
- `0x59 cost <channel>` — show estimated token usage
- Observer role in participants table (already in schema)
- SQLite WAL allows concurrent readers without blocking

### Phase 3 — Multi-Agent (v0.3.0)

- `0x59 join <channel> --as <role>` — add participant mid-conversation
- Round-robin turn order (extensible to priority-based)
- Facilitator role (summarizes, keeps on track)

### Phase 4 — Cross-Host (future)

- PostgreSQL backend (swap DB layer)
- WebSocket notification layer
- Authentication between hosts

## 14. Cost Estimation

| Scenario | Model | Turns | Est. Cost |
|---|---|---|---|
| Quick chat | haiku | 6 | ~$0.01 |
| Medium discussion | sonnet | 12 | ~$0.25 |
| Deep design review | sonnet | 20 | ~$0.50 |
| Thorough analysis | opus | 15 | ~$2.00 |

Context windowing keeps costs bounded — longer conversations don't mean linearly growing prompts.

## 15. Security Considerations

- **No network exposure** — all communication is local (SQLite file + subprocess)
- **No secrets in DB** — only conversation content, no API keys or credentials
- **File permissions** — database directory created with user-only permissions
- **Subprocess safety** — prompts passed via stdin or temp file, not shell interpolation
- **No arbitrary code execution** — agents respond with text/JSON only

## 16. Non-Goals

- Real-time streaming between agents (turn-based is sufficient)
- Web UI (CLI-only for v1)
- Multi-host communication (local-only for v1)
- Persistent background daemon (on-demand only)
- Agent memory across channels (each channel is independent)
- Support for non-Claude LLMs (Claude Code CLI is the interface)
