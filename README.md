# agent-top

Live terminal dashboard for monitoring Claude Code sessions and agents.
<img width="2056" height="1286" alt="image" src="https://github.com/user-attachments/assets/e41ddfdf-78c9-43da-90bc-4ecb51f8b7f8" />


**Requires:** macOS, Python 3, [iTerm2](https://iterm2.com) (for transcript tab opening)

## Setup

```bash
uv tool install git+https://github.com/kingsotn-twelve/agent-top
agent-top --setup
```

`--setup` copies `ccnotify.py` to `~/.claude/ccnotify/` and prints the hook config to merge into `~/.claude/settings.json`. It won't overwrite an existing `ccnotify.py`.

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
