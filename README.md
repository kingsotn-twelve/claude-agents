# claude-agents

Live terminal dashboard for monitoring Claude Code sessions and agents.

<img width="2168" height="1397" alt="image" src="https://github.com/user-attachments/assets/fe40f379-becf-47bb-a93a-fbc48ccab12d" />


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
    ],
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [{"type": "command", "command": "path/to/ccnotify.py PreToolUse"}]
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

Claude will launch Task agents that show up nested under their parent session with live elapsed timers. As each finishes, it moves to HISTORY. This is the quickest way to verify hooks are wired correctly and the dashboard is rendering.

## How it works

- **ccnotify.py** — Claude Code hook handler that logs session, agent, and tool lifecycle events to a SQLite database
- **claude-agents** — curses TUI that polls the database and renders a live tree-view dashboard

Sessions are tracked via `UserPromptSubmit` (start) and `Stop` (end). Agents are tracked via `SubagentStart` and `SubagentStop`. Tool usage is tracked via `PreToolUse`.

## What it shows

```
 SESSIONS (2 running · 3 agents)
 ⠹   1m23s 15b04e implement dark mode
   ├ ⠹  45s Explore a3f82bc
   └ ⠹  12s Plan    b9d1e34
 ⠹     14s a3f82b fix auth bug
   └ ⠹   8s Bash    c7a2f90
 ◦   5m02s 9c1d3a (waiting)
   └ Read→handler.go  Grep→"auth"
```

| Element | Description |
|---------|-------------|
| Session line | Active Claude session with spinner, elapsed time, session ID, and prompt text. Green = running, yellow/dim = waiting for input |
| Child agents | Running subagents (Explore, Plan, Bash, etc.) nested under their parent session with `├`/`└` connectors |
| Tool feed | Last 3 tool calls shown inline for sessions without agents (e.g. `Read→file.go`, `Bash→make test`, `Grep→"auth"`) |
| History | Interleaved timeline of completed agents (▸) and prompts |

### Session cleanup

When a session stops, all its running agents are automatically marked as stopped. Orphan agents (from crashes or missed Stop events) render with an `(orphan)` tag until the 2-hour session expiry.
