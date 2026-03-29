# Roadmap

Current version: **0.1.0** (alpha)

This document tracks known issues and planned improvements across three areas: Python/uv best practices, CI hardening, and code gaps.

---

## 1. Python/uv Best Practices Alignment

### 1.1 Add `py.typed` marker (PEP 561)

The project runs `mypy --strict` but has no `src/zx59/py.typed` file. Without it, downstream consumers running mypy against the installed package will silently treat it as untyped.

- Create empty `src/zx59/py.typed`
- Verify hatchling includes it in the wheel

### 1.2 Add `.python-version` file

uv uses `.python-version` to pin the interpreter for `uv sync` and `uv run`. Without it, each developer's default Python is used, which can diverge from CI.

- Create `.python-version` with `3.12` (or whichever version the team standardizes on)

### 1.3 Fix `exclude-newer` to use absolute date

`pyproject.toml` has `exclude-newer = "7 days"` — a relative span that drifts with wall-clock time. This undermines the supply-chain pinning intent (commit `6cf91c3`). The lock file already records an absolute timestamp.

- Replace with an absolute ISO 8601 date, e.g. `"2026-03-29T00:00:00Z"`
- Update deliberately when upgrading dependencies

### 1.4 Expand ruff rule sets

Current: `["E", "F", "I", "UP", "B", "SIM"]`

Missing rule sets that align with the project's strict posture:

- `RUF` — Ruff-specific rules (includes `RUF100` for unused `# noqa` directives)
- `PTH` — enforces `pathlib.Path` over `os.path` (relevant for a CLI that handles file paths)
- `C4` — flags unnecessary comprehension patterns

### 1.5 Add mypy to pre-commit hooks

Pre-commit runs ruff but not mypy. Type regressions only surface in CI, not locally at commit time. Since the project is stdlib-only, there are no stub-package complications.

```yaml
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: uv run mypy src
      language: system
      types: [python]
      pass_filenames: false
```

### 1.6 Set restrictive DB directory permissions

`db.py` creates the data directory with default permissions (~0o755 after umask). The spec (section 15) says "user-only permissions."

- Change `path.parent.mkdir(parents=True, exist_ok=True)` to include `mode=0o700`

---

## 2. CI Pre-flight and Pre-checks

### 2.1 Replace curl-pipe-sh with pinned uv setup

Every CI job fetches uv via `curl -LsSf https://astral.sh/uv/install.sh | sh` with no integrity check. This is a supply-chain risk — strictly worse than a pinned Action with a SHA.

- Switch to `astral-sh/setup-uv@v5` pinned to a commit SHA, or
- Pin to an explicit uv version with checksum verification

### 2.2 Fix coverage enforcement (currently a silent no-op)

`pyproject.toml` sets `fail_under = 80` but CI runs `pytest --cov=zx59 --cov-report=xml` only. The `fail_under` check requires `--cov-report=term` or `--cov-fail-under=80` on the command line.

- Add `--cov-fail-under=80` to the CI pytest command

### 2.3 Add quality gate before PyPI publish

The release workflow goes checkout -> build -> publish with no tests. A broken tag push publishes a broken package.

- Run `uv run pytest` before `uv build`
- Add a smoke test: `uv run python -c "import zx59"`
- Consider making release `needs: [lint, test]`

### 2.4 Pass matrix Python version to uv

The test matrix sets Python versions via `setup-python` but `uv sync` ignores it and uses its own resolver.

- Use `uv sync --python ${{ matrix.python-version }}`

### 2.5 Switch to OIDC Trusted Publisher for PyPI

Currently uses a long-lived `PYPI_TOKEN` secret. PyPI Trusted Publisher (OIDC) eliminates the stored secret entirely.

- Add `id-token: write` to release job permissions
- Use `uv publish --trusted-publishing always`

### 2.6 Add missing CI checks

- **Dependency audit**: `uv run pip-audit` (supply-chain defense)
- **Build verification**: run `uv build` in the test matrix to catch packaging issues before release
- **Pre-commit in CI**: `pre-commit run --all-files` to enforce trailing-whitespace, YAML/TOML checks
- **macOS coverage**: the macOS test job runs without `--cov`

---

## 3. Code Gaps

### Bugs

#### 3.1 Migration guard breaks when second migration is added

`db.py:129-133` — The `>=` comparison combined with `user_version = max + 1` is accidentally correct for one migration but will re-run migration N when migration N+1 is introduced.

- Fix: store `user_version` as the last applied migration index and use `version > current_version`, or change to `version >= current_version` with `user_version` meaning "next to apply"

#### 3.2 Decision detection is wrong for 3+ agents

`coordinator.py:98-106` — The single `pending_decision` boolean allows non-consecutive agents to trigger a false decision in a 3+ agent round-robin.

- Fix: track which agent set `pending_decision` and verify the confirming agent is different, or validate exactly 2 participants at run start

#### 3.3 `window_messages` has dead `max_tokens` parameter

`context.py:13` — The `max_tokens` parameter is declared but never used. Windowing is purely message-count-based, not token-aware as the spec describes.

- Fix: remove the parameter (honest API), or implement token-sum windowing

### Gaps

#### 3.4 `watch` command is missing

Listed as v0.1.0 in `specs.md` (section 6, Phase 1). Not implemented. Referenced in spec examples.

- Either implement it or move it to a later phase in the spec

#### 3.5 `cost` command is missing

Listed in the spec's CLI table. Not in the parser or command map.

- Either implement it or remove from spec

#### 3.6 Context windowing drops messages without summarization

The spec describes summarizing dropped messages via `claude -p --model haiku`. The implementation silently drops them. This is a deliberate simplification but diverges from the spec.

- Document the simplification, or implement summarization

### Quality

#### 3.7 `export --file` bypasses path validation

`cli.py:192-200` — When the user provides `--file`, no `validate_export_name` check is applied. The artifact name is validated, but the user-supplied path is not. This is arguably by-design (user controls their own machine), but the asymmetry should be documented.

#### 3.8 Linux `notify-send` passes unsanitized Pango markup

`notify.py:27-30` — macOS path escapes backslashes and quotes; Linux path passes raw strings. `notify-send` interprets Pango markup tags in the message body.

#### 3.9 `FakeClaude` raises `StopIteration` on exhaustion

`conftest.py:31` — When a test supplies too few responses, `next()` on an exhausted iterator raises `StopIteration` instead of a clear error message.

- Fix: use a list index and raise `AssertionError("FakeClaude: no more responses")`

---

## Priority Order

**Do first** (bugs and safety):
1. Fix migration guard (3.1)
2. Fix CI coverage enforcement (2.2)
3. Fix `exclude-newer` to absolute date (1.3)
4. Add quality gate before PyPI publish (2.3)
5. Replace curl-pipe-sh in CI (2.1)

**Do next** (correctness and standards):
6. Fix decision detection for 3+ agents (3.2)
7. Remove dead `max_tokens` parameter (3.3)
8. Add `py.typed` marker (1.1)
9. Add `.python-version` (1.2)
10. Expand ruff rules (1.4)

**Do later** (polish and features):
11. Add mypy to pre-commit (1.5)
12. Set DB directory permissions (1.6)
13. Switch to OIDC publishing (2.5)
14. Add missing CI checks (2.6)
15. Pass matrix Python to uv (2.4)
16. Implement or defer `watch` / `cost` commands (3.4, 3.5)
17. Fix FakeClaude exhaustion error (3.9)
18. Document `export --file` behavior (3.7)
