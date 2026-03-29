# Using 0x59

## Quick start

Ask two AI agents to discuss any topic:

```bash
0x59 chat "Should we use JWT or session cookies for our API?"
```

That's it. Two agents — a proposer and a challenger — will debate until they agree or hit the turn limit. You'll see a summary when they finish.

## Commands

### `chat` — Quick discussion

```bash
0x59 chat "Your topic here"
```

Uses two default agents:
- **proposer**: proposes solutions and considers trade-offs
- **challenger**: stress-tests proposals and pushes for clarity

Options:
- `--model MODEL` — which Claude model to use (`haiku`, `sonnet`, `opus`). Default: `sonnet`
- `--max-turns N` — stop after N turns even if no decision. Default: `20`

```bash
# Cheaper, faster discussion with haiku
0x59 chat "Tabs vs spaces?" --model haiku --max-turns 6
```

### `discuss` — Formal discussion with custom roles

For more control over who's debating and what they focus on:

```bash
0x59 discuss "Auth middleware design" \
  --agent architect "Pragmatic backend architect. Favor simplicity." \
  --agent reviewer "Security reviewer. Challenge assumptions." \
  --agenda "1. Token storage
2. Session expiry policy
3. Refresh token strategy" \
  --model sonnet \
  --max-turns 15
```

Options:
- `--agent ID PROMPT` — define an agent with a role description (use multiple times for more agents)
- `--agenda TEXT` — structured agenda for the discussion
- `--model MODEL` — model for all agents. Default: `sonnet`
- `--max-turns N` — turn limit. Default: `20`

If you don't specify `--agent`, the same default proposer/challenger pair is used.

### `ls` — List past discussions

```bash
0x59 ls                # all discussions
0x59 ls --open         # still in progress
0x59 ls --decided      # reached a decision
0x59 ls --closed       # manually closed
```

### `log` — Read a full transcript

```bash
0x59 log <channel-id>
```

The channel ID is shown when you start a discussion and in `0x59 ls` output.

### `decision` — See just the decision

```bash
0x59 decision <channel-id>
```

### `artifacts` — List produced documents

Agents can produce documents (code, design docs, specs) during discussion:

```bash
0x59 artifacts <channel-id>
```

### `export` — Save an artifact to a file

```bash
0x59 export <channel-id> output.md
```

If you omit the filename, it uses the artifact's original name.

### Global options

- `--db PATH` — use a different database file instead of the default location

## How decisions work

Decisions require **both agents to agree in consecutive turns**. One agent can't unilaterally end the conversation.

```
Agent A says "I think we've agreed" (decision_reached = true)  --> pending
Agent B says "Yes, agreed"          (decision_reached = true)  --> decision confirmed
Agent B says "Wait, one more thing" (decision_reached = false) --> back to discussion
```

This ensures genuine consensus, not one-sided declarations.

## Cost awareness

| Scenario | Model | Turns | Estimated cost |
|---|---|---|---|
| Quick chat | haiku | 6 | ~$0.01 |
| Medium discussion | sonnet | 12 | ~$0.25 |
| Deep design review | sonnet | 20 | ~$0.50 |

Use `--model haiku` and low `--max-turns` for cheap exploratory chats. Save `sonnet` or `opus` for decisions that matter.

## Tips

- **Be specific in your topic.** "Design the auth middleware" produces better results than "auth stuff".
- **Use agendas** for multi-part decisions. Agents stay more focused.
- **Custom agent roles** shape the conversation. A "security reviewer" will focus differently than a "UX advocate".
- **Start with fewer turns** (6-10) to test the waters before committing to a long discussion.
- **Export artifacts** — agents sometimes produce useful documents (code samples, decision records) during discussion.
