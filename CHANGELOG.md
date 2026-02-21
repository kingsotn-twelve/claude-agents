# Changelog

## v0.7.0 — Feb 20, 2026

### DETAIL panel navigation

Press `l` on a selected item to focus the DETAIL panel. `j`/`k` then scrolls through tool events, task lists, and transcript content. `h` or `Esc` returns to the left panel. The focused panel highlights with a cyan border and `▶ DETAIL` indicator.

### Session tool timeline in DETAIL

Selecting a session shows its recent tool calls (including MCP) with timestamps. Scroll through them with `l` then `j`/`k`.

### Stats time ranges

`h`/`l` when nothing is selected cycles STATS through 1h, 1d, 7d, 30d, and all. Active range shows as `[7d]` in the panel title.

### Game of Life improvements

50 gen/s with optimized step function. Resizing the terminal no longer resets the simulation — the grid crops/extends to fit. `--game-of-life` flag to enable, welcome screen on first launch.

---

## v0.6.1 — Feb 20, 2026

### Game of Life fixes

Centered welcome screen with shorter copy. Life now shows even when idle (no active sessions) using a fallback seed.

---

## v0.6.0 — Feb 20, 2026

### Layout overhaul

The left panel is now four stacked sections: TEAMS, SESSIONS, HISTORY, and STATS. SESSIONS shows inline tool events under each session row (merged from the old LIVE panel). HISTORY is capped at 8 rows. STATS (AGENTS/TOOLS rankings) moved from the right panel to bottom-left so it's always visible. The right panel is now DETAIL (only when selected) plus an optional Game of Life animation.

### Navigate everything with j/k

Sessions, teammates, agents, and history items are all selectable. Navigate down through SESSIONS into HISTORY — selecting a completed agent opens its transcript in iTerm2. The DETAIL panel sizes itself to fit its content instead of taking a fixed 2/3 of the panel.

### Stats time ranges

Press `h`/`l` to cycle the STATS panel through five time windows: 1h, 1d, 7d, 30d, and all. The active range shows as `[7d]` in the panel title. DB queries refresh immediately when you switch.

### Selection colors

Selected rows now use proper color pairs (white/cyan/yellow on dark gray) instead of the old `A_REVERSE` inversions that made everything unreadable.

### Conway's Game of Life

Run with `--game-of-life` to fill the right panel with a cellular automaton. Each session gets its own universe seeded from its prompt text. A 5-second welcome screen explains the rules before the simulation begins. Cells are color-coded by density: dim (sparse), cyan, green, yellow (packed).

---

## v0.5.2 — Feb 20, 2026

### Inline DETAIL panel

On narrow terminals (< 100 cols), selecting a teammate or agent now shows the DETAIL panel inline — replacing the HISTORY panel — instead of showing nothing. Press Esc to deselect and get HISTORY back.

---

## v0.5.1 — Feb 20, 2026

### Self-update restored

`claude-agents --update` is back. Fetches the latest version from GitHub and replaces the binary in-place.

---

## v0.5.0 — Feb 20, 2026

### Task Progress Tracking

The TEAMS panel title now shows a visual progress bar instead of raw icon counts — `██▓░░ 2/5` tells you at a glance how far along the team is. Select a teammate and the DETAIL panel opens with a richer task view: a 10-char progress header with percentage and status breakdown, blocked tasks marked with `⊘` in red, `[@owner]` tags on every task, and in-progress tasks highlighted in yellow.

### Team Member Status

Team members now show context-aware status icons instead of a uniform pulsing animation. `◉` green means the member is actively using tools (last 15s), `◎` yellow means thinking (session active, no recent tools), and `○` dim means idle or waiting for user input. Each member also shows their current in-progress task on a second line underneath, using `activeForm` when available.

```
├─ ◉  3m  abc123  researcher   ⣿⣷⣦⣄⣀⠀⠀⠀⠀⠀
│     ● Implementing auth endpoints
├─ ◎  3m  def456  implementer  ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
└─ ○  3m  789abc  reviewer     ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
      ● Reviewing PR #42
```

### Team Metrics in Stats View

When no teammate is selected, the DETAIL panel now shows a TEAMS section above the existing agent/tool stats. Each team gets a completion bar with status breakdown, plus per-member task counts with mini progress bars — so you can see who's carrying the load without selecting anyone.

### Smoother Rendering

The render loop now runs at 200ms (5 FPS) instead of 1s, making spinner animations and keyboard navigation feel as fluid as btop. DB queries are cached and only refreshed every ~2s to keep things lightweight.

---

## v0.4.1 — Feb 20, 2026

### Esc to deselect

Pressing `Esc` while an agent or teammate is selected now clears the selection and returns the right panel to the stats view. Previously the only way back was to quit and reopen. `q`/`Q` still quits; `Esc` no longer does.

---

## v0.4.0 — Feb 20, 2026

### Agent Teams

The dashboard now understands the difference between subagents (spawned via `Task` inside a session) and agent team teammates (separate, independent Claude Code sessions coordinated as a team). Previously, team members appeared as anonymous solo sessions with no grouping and no visibility into the shared task list.

A new **TEAMS** section sits above SESSIONS and groups active teammates under their team name, showing live task counts at a glance — `1✓ 2● 2○` for completed, in-progress, and pending. Team members are excluded from the solo SESSIONS list to avoid double-display. Navigate with `j/k` to select any teammate, and the right panel switches from transcript preview to the team's full task list, sorted running-first.

```
 TEAMS (test-team · 5 tasks  1✓ 2● 2○)
 ├─ ◉  3m  b095b7  researcher
 ├─ ◉  3m  db6550  implementer
 └─ ◉  3m  1f2a1a  reviewer
```

Team membership is resolved by reading `~/.claude/teams/{name}/config.json` and task files from `~/.claude/tasks/{name}/` on every refresh. A new `team_session` DB table is populated by the new `TeammateIdle` hook as a fallback for teammates not yet in the config files. Desktop notifications fire on `TeammateIdle` ("Idle: researcher") and `TaskCompleted` ("✓ Implement auth endpoints").

To test without running a real team, use the new `test-teams.sh` script — it writes fake team config and task files, inserts sessions into the DB, and simulates a task completing mid-run.

```bash
./test-teams.sh          # 20s run
./test-teams.sh 60       # 60s run
```

---

## v0.3.1 — Feb 20, 2026

### Smarter session staleness

Sessions killed without `Stop` firing (closed terminal, Ctrl+C mid-turn) used to stay visible in the dashboard for up to 2 hours. Now a session is only shown as active if it has had tool activity in the last 10 minutes, is waiting for user input within 30 minutes, or was just started within 5 minutes. Stale sessions disappear in under a minute.

When `Stop` does fire, it now clears all un-stopped rows for the session — not just the latest — so any rows accumulated from previous failures are cleaned up atomically.

---

## v0.3.0 — Feb 19, 2026

### Install script

A new `install.sh` puts everything in the right place so `claude-agents` works from any directory — no more `./claude-agents` from the repo. It copies `ccnotify.py` to `~/.claude/ccnotify/` and the binary to `~/.local/bin/`, then prints the exact hook config to paste into `~/.claude/settings.json`.

```bash
git clone https://github.com/kingsotn-twelve/claude-agents
cd claude-agents
./install.sh
```

### Test script

`test-agents.sh` spins up fake agents directly in the database so you can verify the dashboard without a live Claude session. Pass optional args to control count and sleep range.

```bash
./test-agents.sh          # 5 agents, 5–20s
./test-agents.sh 3 2 8    # 3 agents, 2–8s
```

### `CLAUDE_AGENTS_DB` env var

Both `claude-agents` and `test-agents.sh` now respect a `CLAUDE_AGENTS_DB` environment variable for pointing at a non-default database location, useful if your `ccnotify.py` is installed somewhere other than `~/.claude/ccnotify/`.

---

## v0.2.3 — Feb 19, 2026

### Dir prefix on tools stats
The TOOLS stats panel now shows `[dirname]` prefixes too, grouped by both directory and tool name — matching the same column-aligned layout as the AGENTS panel.

---

## v0.2.2 — Feb 19, 2026

### Aligned columns in agents stats panel
The `[dir]` and `AgentType` columns in the AGENTS stats panel are now dynamically aligned — widths are computed from the current data so all rows line up cleanly regardless of path or type name length.

---

## v0.2.1 — Feb 19, 2026

### Dir prefix in stats panel
The AGENTS stats panel on the right now shows `[dirname] AgentType` per row, grouped by both directory and agent type — so `[.claude] Explore` and `[rodeo] Explore` appear as separate entries. No more truncation on agent type names.

### Dir prefix in transcript preview header
The selected agent header now reads `aid · [dirname] AgentType · dur`.

---

## v0.2.0 — Feb 19, 2026

### Directory prefix on agents
Agents now show a cyan `[dirname]` tag before their type so you can tell at a glance which project they belong to — e.g. `[.claude] Explore` vs `[rodeo] Plan`. Derived from the agent's working directory.

### Cleaner duration display
Removed green/yellow/red color coding on session durations. All durations now render in a single consistent color.

---

## v0.1.2 — Feb 19, 2026

### Self-update
```
claude-agents --update
```
Fetches the latest version from GitHub and replaces the binary in-place. Prints `already up to date` if you're current, or `updated v0.1.1 → v0.1.2` on success.

---

## v0.1.1 — Feb 19, 2026

### Fixed: Unknown Agent Pollution
The stats panel was showing `unknown ████████ 151` — agents fired by Claude Code without an `agent_type` in the hook payload were being stored as `"unknown"` and counted in usage stats. These are now silently ignored, and the 151 stale records have been cleaned from the database.

---

## v0.1.0 — Feb 19, 2026

### Usage Stats Panel
See what's been running. A live stats panel shows your top agent types and most-used tools over the last 7 days, rendered as bar charts in the right column.

### Transcript Preview
Select any agent in the tree and get an inline preview of its output — last few lines pulled live from the `.jsonl` transcript, right in the dashboard.

### iTerm2 Integration
Press `Enter` on a selected agent to open its transcript in a new iTerm2 tab with `tail -f`. Jump straight into what the agent was doing without leaving your workflow.

### `--version` and `--help`
```
claude-agents --version   # claude-agents v0.1.0
claude-agents --help      # usage + options
```

---

*See the full diff on [GitHub](https://github.com/kingsotn-twelve/claude-agents/releases/tag/v0.1.0).*
