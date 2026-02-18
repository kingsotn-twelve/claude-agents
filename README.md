# claude-agents

Live terminal dashboard for monitoring Claude Code sessions and agents.

```
 ⠹ CLAUDE AGENTS  2 sessions · 3 agents     23:15:42
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SESSIONS (2 running · 1 waiting)
 ⠹   1m23s 15b04e implement dark mode for settings page
 ⠹     14s a3f82b fix auth token refresh bug
 ◦   5m02s 9c1d3a (waiting for input)

 AGENTS (3)
 ⠹   1m05s Explore  a3f82bc
 ⠹     32s Plan     b9d1e34
 ⠹      8s Bash     c7a2f90
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 HISTORY
 23:14:21    12s ▸ Explore
 23:14:05  2m31s fix the login redirect loop
 23:11:22     6s ▸ Bash
 23:10:50  1m42s add retry logic to webhook handler

 q=quit │ 1s refresh
```

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
