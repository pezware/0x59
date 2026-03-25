# 0x59

Lightweight inter-agent communication for Claude Code instances on a single host.

Two Claude Code agents discuss a topic, reach a decision, and produce artifacts — all stored in a local SQLite database with zero external dependencies.

## How It Works

```
Human (CLI)
     |
     v
 Coordinator        turn-based loop
     |
  +--+--+
  v     v
claude -p    claude -p      called sequentially via subprocess
(Agent A)    (Agent B)
  +--+--+
     |
     v
  SQLite              messages, decisions, artifacts
```

The coordinator calls `claude -p` for each agent in turn. Each agent sees the conversation history, responds with structured JSON, and signals when consensus is reached. No daemon, no server — runs on demand and exits.

## Install

```bash
# Run without installing (recommended)
uvx zx59

# Or install globally
pip install zx59

# Or with pipx
pipx install zx59
```

**Requires**: Python 3.10+ and [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed.

## Quick Start

```bash
# Quick chat — two default agents discuss your topic
0x59 chat "Should we use JWT or session cookies for our API?"

# Formal discussion with specific roles and agenda
0x59 discuss "Auth middleware design" \
  --agent architect "Pragmatic backend architect. Favor simplicity." \
  --agent reviewer "Security reviewer. Challenge assumptions." \
  --agenda "1. Token storage
2. Session expiry policy
3. Refresh token strategy" \
  --model sonnet \
  --max-turns 15

# Review results
0x59 ls                          # list all channels
0x59 log <channel-id>            # full transcript
0x59 decision <channel-id>       # just the decision
0x59 artifacts <channel-id>      # list produced documents
0x59 export <channel-id> out.md  # export artifact to file
```

## Commands

| Command | Description |
|---|---|
| `0x59 chat <topic>` | Quick 2-agent chat with default roles |
| `0x59 discuss <topic>` | Formal discussion with custom agents |
| `0x59 log <channel-id>` | Print full transcript |
| `0x59 decision <channel-id>` | Print decision summary |
| `0x59 artifacts <channel-id>` | List produced documents |
| `0x59 export <channel-id> [file]` | Export artifact to file |
| `0x59 ls` | List channels (`--open`, `--decided`, `--closed`) |

### Global Options

| Option | Description |
|---|---|
| `--db PATH` | Override database path |

### Chat/Discuss Options

| Option | Default | Description |
|---|---|---|
| `--model MODEL` | `sonnet` | Model to use (`haiku`, `sonnet`, `opus`) |
| `--max-turns N` | `20` | Maximum conversation turns |
| `--agent ID PROMPT` | — | Define agent with role (repeatable) |
| `--agenda TEXT` | — | Discussion agenda |

## Decision Protocol

Decisions require **mutual agreement** — both agents must set `decision_reached: true` in consecutive turns. One agent cannot unilaterally end the conversation.

```
Agent A: decision_reached=true   -> pending
Agent B: decision_reached=true   -> confirmed, channel decided
Agent B: decision_reached=false  -> reset, conversation continues
```

## Cost Estimation

| Scenario | Model | Turns | Est. Cost |
|---|---|---|---|
| Quick chat | haiku | 6 | ~$0.01 |
| Medium discussion | sonnet | 12 | ~$0.25 |
| Deep design review | sonnet | 20 | ~$0.50 |

## Data Storage

Conversations are stored in a local SQLite database:
- **macOS**: `~/Library/Application Support/0x59/channels.db`
- **Linux**: `~/.local/share/0x59/channels.db`

Override with `--db /path/to/file.db`.

## Development

```bash
git clone https://github.com/pezware/0x59.git
cd 0x59
uv sync
uv run pytest                        # run tests
uv run ruff check src tests          # lint
uv run mypy src                      # type check
uv run 0x59 --help                   # run locally
```

See [CLAUDE.md](CLAUDE.md) for contributor guidelines and [docs/specs.md](docs/specs.md) for the full specification.

## License

MIT
