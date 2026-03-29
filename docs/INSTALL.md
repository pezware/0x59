# Installing 0x59

## Before you start

You need two things on your computer:

1. **Python 3.10 or newer** — check by opening a terminal and typing:
   ```
   python3 --version
   ```
   If you see `Python 3.10` or higher, you're good. If not, install Python from [python.org](https://www.python.org/downloads/).

2. **Claude Code CLI** — this is the tool that 0x59 uses to talk to Claude. Install it by following the [Claude Code setup guide](https://docs.anthropic.com/en/docs/claude-code).

## Install options

Pick whichever method you're most comfortable with.

### Option A: Run without installing (recommended)

This runs 0x59 directly without permanently installing it:

```
uvx zx59
```

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) for this. It's a fast Python package manager. Install it with:

```
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Option B: Install with pip

```
pip install zx59
```

After installing, the `0x59` command is available in your terminal.

### Option C: Install with pipx

[pipx](https://pipx.pypa.io/) installs Python tools in isolated environments so they don't interfere with other packages:

```
pipx install zx59
```

## Verify it works

After installing, run:

```
0x59 --help
```

You should see a list of available commands. If you get "command not found", make sure your Python scripts directory is in your system PATH.

## Where data is stored

0x59 saves conversations in a local database file:

- **macOS**: `~/Library/Application Support/0x59/channels.db`
- **Linux**: `~/.local/share/0x59/channels.db`

You can override this with `--db /your/path/here.db` on any command.

## Updating

```
# If installed with pip
pip install --upgrade zx59

# If installed with pipx
pipx upgrade zx59

# If using uvx, you always get the latest version automatically
```

## Uninstalling

```
# If installed with pip
pip uninstall zx59

# If installed with pipx
pipx uninstall zx59
```

The database file is not removed automatically. Delete it manually if you no longer need your conversation history.
