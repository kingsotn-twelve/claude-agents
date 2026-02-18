# claude-agents

Live terminal dashboard for monitoring Claude Code sessions and agents.

![Uploading image.png…]()

## Setup

### 1. Install hooks

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SubagentStart": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "path/to/ccnotify.py SubagentStart"}]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "path/to/ccnotify.py SubagentStop"}]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "path/to/ccnotify.py UserPromptSubmit"}]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "path/to/ccnotify.py Stop"}]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "path/to/ccnotify.py Notification"}]
      }
    ]
  }
}
```

### 2. Run the dashboard

```bash
./claude-agents
```

Open in a split pane alongside your Claude Code session. Press `q` to quit.

## Test it

Open the dashboard in one pane, then ask Claude to spin up background agents in another:

```
spin up 5 background agents that sleep for random durations between 5-20 seconds
```

Claude will launch Task agents that show up in the AGENTS section with live elapsed timers. As each finishes, it moves to HISTORY. This is the quickest way to verify hooks are wired correctly and the dashboard is rendering.

## How it works

- **ccnotify.py** — Claude Code hook handler that logs session and agent lifecycle events to a SQLite database
- **claude-agents** — curses TUI that polls the database and renders a live dashboard

Sessions are tracked via `UserPromptSubmit` (start) and `Stop` (end). Agents are tracked via `SubagentStart` and `SubagentStop`.

## What it shows

| Section | Data |
|---------|------|
| Sessions | Active Claude sessions with elapsed time, session ID, and prompt text. Green = running, yellow = waiting for input |
| Agents | Running subagents (Explore, Plan, Bash, etc.) with elapsed time and agent type |
| History | Interleaved timeline of completed agents (▸) and prompts |
