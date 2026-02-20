# claude-agents

Live terminal dashboard for monitoring Claude Code sessions and agents.

<img width="2168" height="1397" alt="image" src="https://github.com/user-attachments/assets/fe40f379-becf-47bb-a93a-fbc48ccab12d" />


## Setup

```bash
git clone https://github.com/kingsotn-twelve/claude-agents
cd claude-agents
./install.sh
```

`install.sh` copies `ccnotify.py` to `~/.claude/ccnotify/` and `claude-agents` to `~/.local/bin/` so it's on your PATH. It also prints the exact hook config to paste into `~/.claude/settings.json`.

### Manual hook config

After running `install.sh`, add the printed block to `~/.claude/settings.json`. It looks like:

```json
{
  "hooks": {
    "SubagentStart":    [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/ccnotify/ccnotify.py SubagentStart"}]}],
    "SubagentStop":     [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/ccnotify/ccnotify.py SubagentStop"}]}],
    "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/ccnotify/ccnotify.py UserPromptSubmit"}]}],
    "Stop":             [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/ccnotify/ccnotify.py Stop"}]}],
    "Notification":     [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/ccnotify/ccnotify.py Notification"}]}],
    "PreToolUse":       [{"matcher": "", "hooks": [{"type": "command", "command": "~/.claude/ccnotify/ccnotify.py PreToolUse"}]}]
  }
}
```

### Run the dashboard

```bash
claude-agents
```

Open in a split pane alongside your Claude Code session. Press `q` to quit.

## Test it

Run the included test script to verify the dashboard without needing a live Claude session:

```bash
./test-agents.sh          # 5 agents, 5–20s
./test-agents.sh 3 2 8    # 3 agents, 2–8s
```

Agents appear nested under a test session with live elapsed timers. As each finishes it moves to HISTORY.

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
