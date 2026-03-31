# Brainstorm Mode — Design Document

> Mixed-participant interactive sessions: human + Claude + Codex brainstorming together.

**Status**: Proposal
**Depends on**: v0.1.0 (core 2-agent chat) — already shipped

---

## 1. Problem Statement

The current `0x59 chat` and `0x59 discuss` commands run batch conversations between Claude agents. The human starts a topic and reads the result afterward. This works for delegation ("go debate this and report back") but not for **brainstorming**.

Think of it like a **local Slack channel** — except instead of colleagues, the participants are Claude, Codex, Gemini, and you. The conversation is loose, exploratory, and shaped by local project context (codebase, CLAUDE.md, skills). Each model brings different strengths and perspectives, and you steer the discussion as a peer.

What's missing today:
- **No mixed-model chat** — Claude talks to Claude, Codex is 1:1 dispatch only
- **No human-in-the-loop** — you read results after, not during
- **No project context influence** — each agent call is isolated, not grounded in the local codebase
- **No persistence** — Slack has history; ad-hoc model calls don't

## 2. Goals

1. **Slack-like experience** — loose, conversational, not formal debate
2. **Multi-model** — Claude, Codex, Gemini, and human in the same channel
3. **Human as peer** — type when it's your turn, steer the conversation
4. **Project-aware** — agents grounded in local codebase context and skills
5. **Same persistence** — SQLite transcript, artifacts, decisions all still work
6. **Backward compatible** — existing `chat`/`discuss` commands unchanged

## 3. Non-Goals (for now)

- Async/concurrent turns (keep sequential simplicity)
- Cross-host participants (Phase 4 in roadmap)
- Streaming output mid-turn (show full response when turn completes)
- Web UI or TUI — stays CLI

## 4. Architecture

### 4.1 Runner Protocol Extension

The existing `ClaudeRunner` protocol is the extensibility seam:

```python
class ClaudeRunner(Protocol):
    def run(self, prompt: str, model: str, json_schema: str,
            *, session_name: str | None = None) -> str: ...
```

New runner implementations:

```
ClaudeRunner (Protocol)
    |
    +-- SubprocessClaudeRunner   # existing: calls `claude -p`
    +-- CodexRunner              # new: calls Codex CLI
    +-- GeminiRunner             # new: calls Gemini CLI
    +-- HumanRunner              # new: prompts stdin for input
    +-- FakeClaude               # existing: test double
```

### 4.2 HumanRunner

Prompts the user for input and wraps it in the expected JSON schema:

```python
class HumanRunner:
    def run(self, prompt: str, model: str, json_schema: str,
            *, session_name: str | None = None) -> str:
        # Display the conversation context (last N messages)
        # Prompt for input via stdin
        # Wrap in {"message": input, "decision_reached": false, "artifacts": []}
        # Return as JSON string
```

Key decisions:
- Show a condensed context summary before each prompt (not the full prompt sent to agents)
- Support special commands: `/decide <summary>` to signal decision, `/artifact <name>` to produce an artifact, `/quit` to leave early
- The human doesn't need a `model` — parameter is ignored

### 4.3 CodexRunner

Calls the Codex CLI and normalizes the plain-text response:

```python
class CodexRunner:
    def run(self, prompt: str, model: str, json_schema: str,
            *, session_name: str | None = None) -> str:
        # Call: codex -q --model <model> "<prompt>"
        # Codex returns plain text, not JSON
        # Wrap in {"message": response, "decision_reached": false, "artifacts": []}
        # Return as JSON string
```

Key decisions:
- Codex doesn't support the structured JSON schema output, so the runner normalizes
- Codex can't produce artifacts or signal decisions — those are human/Claude capabilities
- Default model: whatever `codex` defaults to; override via `--agent codex gpt-5.4`

### 4.4 GeminiRunner

Calls the Gemini CLI similarly:

```python
class GeminiRunner:
    def run(self, prompt: str, model: str, json_schema: str,
            *, session_name: str | None = None) -> str:
        # Call: gemini -q --model <model> "<prompt>"
        # Same normalization as CodexRunner
```

Key decisions:
- Same pattern as CodexRunner — plain text in, JSON schema wrapper out
- Gemini CLI must be installed separately (`npm install -g @anthropic-ai/gemini` or equivalent)
- Each external runner follows the same thin-wrapper pattern: call CLI, normalize response

### 4.5 Coordinator Changes

The coordinator currently assumes all runners are the same type:

```python
# Current: single runner for all agents
class Coordinator:
    def __init__(self, db: DB, runner: ClaudeRunner) -> None:
```

Brainstorm mode needs **per-agent runners**:

```python
# Proposed: runner resolved per agent
class Coordinator:
    def __init__(self, db: DB, runner: ClaudeRunner | None = None,
                 runner_factory: Callable[[Participant], ClaudeRunner] | None = None) -> None:
```

The `runner_factory` maps each participant to its runner based on participant metadata (e.g., a `runner_type` field: `"claude"`, `"codex"`, `"human"`).

Backward compatible: if only `runner` is provided, all agents use it (existing behavior).

## 5. CLI Interface

### 5.1 New Command: `0x59 brainstorm`

```bash
# Quick brainstorm: you + Claude + Codex (default participants)
0x59 brainstorm "How should we redesign the auth flow?"

# You + Claude + Codex + Gemini
0x59 brainstorm "API design for webhooks" \
    --agent claude proposer "Explore ideas" \
    --agent codex critic "Poke holes" \
    --agent gemini reviewer "Offer alternatives" \
    --agent human me

# Full control
0x59 brainstorm "Migration strategy" \
    --agent claude:sonnet architect "Design the approach" \
    --agent codex challenger "Find blind spots" \
    --agent gemini:pro analyst "Compare with industry patterns" \
    --agent human lead \
    --max-turns 20
```

### 5.2 Agent Syntax

Extended `--agent` format: `--agent <runner:model> <id> [prompt]`

- `claude` / `claude:sonnet` / `claude:opus` — SubprocessClaudeRunner
- `codex` / `codex:gpt-5.4` — CodexRunner
- `gemini` / `gemini:pro` — GeminiRunner
- `human` — HumanRunner (model ignored)

### 5.3 Default Agents

When no `--agent` flags provided:

```
agent claude  proposer  "Propose ideas and explore solutions"
agent codex   critic    "Challenge assumptions and find blind spots"
agent human   me        (no system prompt)
```

This gives the simplest invocation a 3-way conversation by default.

### 5.4 Project Context

Each agent receives local project context appropriate to its runner:
- **Claude** — already reads CLAUDE.md, codebase context via `claude -p`
- **Codex** — pass relevant file contents or summaries in the prompt
- **Gemini** — same as Codex, prompt-injected context
- **Human** — you already know your project

The conversation topic + local codebase context shapes depth and direction naturally, just like domain expertise shapes a Slack discussion.

## 6. Interactive Turn Display

Each turn renders immediately:

```
── Turn 3/15 ── proposer (claude:sonnet) ──────────
We could use event-driven webhooks with retry...

── Turn 4/15 ── critic (codex) ────────────────────
What about idempotency? If a webhook fires twice...

── Turn 5/15 ── me (human) ────────────────────────
> Good point. Let's require an idempotency key.
> /decide Webhooks with idempotency keys, retry with exponential backoff
```

## 7. Participant Schema Extension

The `participants` table needs a `runner_type` column:

```sql
ALTER TABLE participants ADD COLUMN runner_type TEXT NOT NULL DEFAULT 'claude'
    CHECK (runner_type IN ('claude', 'codex', 'gemini', 'human'));
```

This is migration 2 (current schema is version 1).

## 8. Open Questions

<!-- TODO: resolve before implementation -->

1. **Turn order for humans** — strict round-robin, or let the human "pass" and interject later? Round-robin is simpler but can feel awkward if you have nothing to say on a turn.

2. **Codex context** — Codex has its own context management. Should we send the full conversation history (like we do for Claude), or a condensed summary? The Codex CLI may have different token limits.

3. **Decision protocol with humans** — currently requires two *different* agents to agree. Should a human `/decide` count as one vote, requiring one agent to confirm? Or should human decisions be authoritative (you're the boss)?

4. **Codex authentication** — requires `codex login` separately. Should `0x59 brainstorm` check for this upfront and fail fast with a helpful message?

## 9. Implementation Stages

### Stage 1: Runner Abstraction

- Add `runner_type` to participant schema (migration 2)
- Add `runner_factory` to Coordinator (backward compatible)
- Add `HumanRunner` with basic stdin prompt
- Tests: FakeClaude + FakeHuman in same conversation

### Stage 2: External Model Runners

- Add `CodexRunner` calling the Codex CLI
- Add `GeminiRunner` calling the Gemini CLI
- Response normalization (plain text -> JSON schema) — shared base
- Availability checks (fail fast if CLI not installed/authed)
- Tests: FakeClaude + FakeCodex + FakeGemini

### Stage 3: CLI & Interactive Mode

- `0x59 brainstorm` command with extended `--agent` syntax
- Interactive display (turn headers, human prompt)
- Special commands: `/decide`, `/artifact`, `/quit`
- Integration tests with FakeClaude + FakeCodex + scripted human input

### Stage 4: Polish

- Context tuning for Codex (may need different windowing)
- Turn-skip / pass for human participants
- Tab completion for special commands
- Update specs.md and usage docs

## 10. Risks

- **External CLI stability** — Codex and Gemini CLIs are external deps that may change. Mitigate: thin wrappers, version pin, fail-fast checks.
- **Interactive testing** — stdin-based tests are fragile. Mitigate: `HumanRunner` accepts an input stream (default stdin, tests pass StringIO).
- **Mixed response quality** — Codex/Gemini can't produce structured output. Mitigate: normalize at the runner boundary, don't push structured requirements onto external models.
- **Zero-dependency principle** — external CLIs are runtime tools, not Python deps. The runners shell out to them just like `SubprocessClaudeRunner` shells out to `claude`. No `pip install` required.

## 11. Success Criteria

- [ ] `0x59 brainstorm "topic"` starts a 3-way session (human + Claude + Codex)
- [ ] Human can type responses, signal decisions, and produce artifacts
- [ ] Full transcript persisted in SQLite, viewable via `0x59 log`
- [ ] Existing `chat`/`discuss` commands unaffected
- [ ] 80%+ test coverage maintained
