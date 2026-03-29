# 0x59

Two AI agents discuss a topic and reach a decision together. Everything is saved locally on your computer.

You give 0x59 a question or topic. It creates two Claude agents with different perspectives — one proposes ideas, the other challenges them. They go back and forth until they agree on an answer. The full conversation and any documents they produce are stored in a local database you control.

No servers, no accounts, no cloud storage. Just a command-line tool that runs on your machine.

## Who is this for?

- **Developers** who want AI-assisted design decisions with built-in devil's advocacy
- **Teams** exploring trade-offs before committing to an approach
- **Anyone** who wants more than a single AI perspective on a problem

## Documentation

| Document | Description |
|---|---|
| [INSTALL.md](INSTALL.md) | How to install 0x59 on your computer |
| [USAGE.md](USAGE.md) | How to use 0x59 — commands, examples, tips |
| [DEVELOPMENT.md](DEVELOPMENT.md) | For contributors — architecture, testing, packaging |
| [ROADMAP.md](ROADMAP.md) | Known issues and planned improvements |
| [specs.md](specs.md) | Full technical specification |

## How it works (30-second version)

```
You ask a question
    |
    v
Agent A proposes an answer
    |
    v
Agent B challenges it
    |
    v
They go back and forth (you set the limit)
    |
    v
Both agree --> Decision saved
```

All conversations are stored in a SQLite file on your machine. You can review transcripts, export documents the agents produced, and list past discussions at any time.

## Requirements

- Python 3.10 or newer
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and working

## License

MIT
