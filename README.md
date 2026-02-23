# agent-top

Live terminal dashboard for monitoring Claude Code sessions and agents.

<img width="2168" height="1397" alt="image" src="https://github.com/user-attachments/assets/12864435-fb1d-4d9d-b5ef-19154db86ebe" />

**Requires:** macOS, Python 3, [iTerm2](https://iterm2.com) (for transcript tab opening)

## Setup

```bash
git clone https://github.com/kingsotn-twelve/agent-top
cd agent-top
./install.sh
```

`install.sh` copies `ccnotify.py` to `~/.claude/ccnotify/` and `agent-top` to `~/.local/bin/`. It then prints the exact hook config to merge into `~/.claude/settings.json`.

### Hook config

`install.sh` prints the hooks block to add to `~/.claude/settings.json`. Merge it into the existing `"hooks"` key (don't replace the whole file):

```json
{
  "hooks": {
    "SubagentStart":    [ ... ],
    "SubagentStop":     [ ... ],
    "UserPromptSubmit": [ ... ],
    "Stop":             [ ... ],
    "Notification":     [ ... ],
    "PreToolUse":       [ ... ]
  }
}
```

### Run the dashboard

```bash
agent-top
```

Open in a split pane alongside your Claude Code session. Press `q` to quit.

## Uninstall

```bash
rm ~/.local/bin/agent-top
rm -rf ~/.claude/ccnotify/
```

Then remove the hooks block from `~/.claude/settings.json`.

## What it shows

```
 SESSIONS (2 running · 3 agents)
 ◎   1m23s 15b04e implement dark mode
   ├ ⠹  45s [rodeo]   Explore a3f82bc
   └ ⠹  12s [rodeo]   Plan    b9d1e34
 ◎     14s a3f82b fix auth bug
   └ ⠹   8s [myapp]   Bash    c7a2f90
 ○   5m02s 9c1d3a (waiting)
   └ Read→handler.go  Grep→"auth"
```

| Element | Description |
|---------|-------------|
| Session line | Active session with spinner, elapsed time, session ID, and prompt. Green = running, dim = waiting for input |
| Child agents | Running subagents nested under their parent with `├`/`└` connectors, showing `[dirname]` tag, type, ID, and elapsed time |
| Tool feed | Last 3 tool calls inline for agentless sessions (e.g. `Read→file.go`, `Bash→make test`) |
| Right panel | 7-day bar charts for top agent types and tools, or live transcript preview when an agent is selected |
| History | Interleaved timeline of completed agents (▸) and finished prompts |

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Select next agent |
| `k` / `↑` | Select previous agent |
| `Enter` | Open selected agent's transcript in a new iTerm2 tab (`tail -f`) |
| `q` | Quit |

## Test it

Verify the dashboard without a live Claude session:

```bash
./test-agents.sh          # 5 agents, 5–20s
./test-agents.sh 3 2 8    # 3 agents, 2–8s
```

Agents appear nested under a test session with live timers. As each finishes it moves to HISTORY.

## How it works

- **ccnotify.py** — Claude Code hook handler. Logs session, agent, and tool lifecycle events to SQLite. Fires macOS desktop notifications with sounds on task complete, waiting for input, and agent done.
- **agent-top** — curses TUI that polls the database every second and renders a live tree-view dashboard.

Sessions are tracked via `UserPromptSubmit` (start) and `Stop` (end). Agents are tracked via `SubagentStart` / `SubagentStop`. Tool usage is tracked via `PreToolUse`.

A session is considered active if it has had tool activity in the last 10 minutes, is waiting for user input (within 30 minutes), or was just started (within 5 minutes). This means sessions killed without `Stop` firing disappear quickly rather than staying visible for hours.

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `AGENT_TOP_DB` | `~/.claude/ccnotify/ccnotify.db` | Path to the SQLite database |

## License

MIT
