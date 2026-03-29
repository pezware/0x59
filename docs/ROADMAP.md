# Roadmap

Current version: **0.1.0** (alpha)

This document tracks completed improvements and remaining work.

---

## Completed

### Python/uv Best Practices

- [x] Add `py.typed` marker (PEP 561) — downstream type checkers now recognize inline annotations
- [x] Add `.python-version` file — pins dev interpreter to 3.12 for uv consistency
- [x] Fix `exclude-newer` to absolute ISO 8601 date — no more wall-clock drift
- [x] Expand ruff rules — added `RUF`, `PTH`, `C4` to match strict project posture
- [x] Add mypy to pre-commit hooks — type regressions caught locally, not just in CI
- [x] Set restrictive DB directory permissions — `mode=0o700` per spec section 15

### CI Hardening

- [x] Pin uv version in CI — `UV_VERSION` env var for reproducible installs (no third-party Actions)
- [x] Fix coverage enforcement — `--cov-fail-under=80` actually enforced now
- [x] Add quality gate before PyPI publish — test + build + smoke test before publish
- [x] Pass matrix Python version to `uv sync` — test matrix actually tests the right interpreter
- [x] Switch to OIDC Trusted Publisher — `uv publish --trusted-publishing always`, no stored API token
- [x] Add pre-commit job to CI — enforces trailing-whitespace, YAML/TOML, merge conflict checks
- [x] Add build verification to lint job — catches packaging issues before release
- [x] Add dependency audit — `pip-audit` in CI lint job
- [x] Upgrade to `actions/checkout@v6` and `actions/setup-python@v6`

### Code Fixes

- [x] Harden migration guard — skip unnecessary `user_version` writes, clarify semantics with docstring
- [x] Fix decision detection for 3+ agents — track proposing agent ID, confirming agent must differ
- [x] Remove dead `max_tokens` parameter from `window_messages` — honest API
- [x] Fix `FakeClaude` exhaustion — clear `AssertionError` instead of cryptic `StopIteration`
- [x] Document `export --file` behavior — CLI help now states any path accepted
- [x] Defer `watch` and `cost` commands to Phase 2 — updated `specs.md` to match
- [x] Escape Pango markup in Linux `notify-send` — prevents unintended HTML rendering
- [x] Document context windowing simplification — spec updated to match implementation
- [x] Escape newlines in macOS notifications — AppleScript strings break on literal newlines
- [x] Add `encoding="utf-8"` to artifact export — prevents corruption on non-UTF-8 locales
- [x] Extract shared exceptions into `errors.py` — decouples coordinator from subprocess runner
- [x] Add `--name` flag to `export` command — select artifact when multiple exist

---

## Remaining

### Features (Phase 2)

Per `specs.md` section 13:

- `0x59 watch <channel>` — live tail a conversation in real-time
- `0x59 cost <channel>` — show estimated token usage
- Observer role support (schema already in place)
- Context windowing with summarization (currently drops middle messages silently)

### Infrastructure

#### PyPI Trusted Publisher setup required

The release workflow is configured for OIDC (`uv publish --trusted-publishing always`), but the PyPI project must be configured as a Trusted Publisher. Follow [PyPI's guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) to link the `pezware/0x59` GitHub repository to the `zx59` PyPI project.
