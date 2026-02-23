# Agent Teams Support — Design

**Date:** 2026-02-20
**Status:** Approved

## Problem

`agent-top` monitors subagents (spawned via `Task` tool, `SubagentStart`/`SubagentStop` hooks) but not agent teams. Agent team teammates are separate, independent Claude Code sessions — not subagents. They show up as anonymous solo sessions in the dashboard with no grouping, and the shared task list is invisible.

## Key Distinctions

| | Subagents | Agent Team Teammates |
|---|---|---|
| Hooks | `SubagentStart` / `SubagentStop` | `TeammateIdle` / `TaskCompleted` |
| Session | Runs inside parent session | Own independent `session_id` |
| Config | n/a | `~/.claude/teams/{name}/config.json` |
| Tasks | n/a | `~/.claude/tasks/{name}/` |

## Solution — Hybrid (file-system + hooks)

### Data Sources

1. **`~/.claude/teams/{name}/config.json`** — member list (`agentId`, `name`, `agentType`). `agentId` is assumed to equal the teammate's `session_id`.
2. **`~/.claude/tasks/{name}/`** — task JSON files with `status: pending|in_progress|completed`.
3. **`team_session` DB table** — populated by `TeammateIdle` hook as a fallback when config files aren't present yet.

### `ccnotify.py` Changes

- New `team_session` table: `(session_id PK, team_name, teammate_name, last_seen_at)`
- `handle_teammate_idle()`: upsert `team_session`, send desktop notification
- `handle_task_completed()`: send desktop notification "Task done: {subject}"
- Register `TeammateIdle` and `TaskCompleted` in `settings.json`

### `agent-top` Dashboard Changes

- `query_teams()`: scans team config files + task files, cross-refs with DB
- **TEAMS section** above SESSIONS — team members excluded from SESSIONS
- `j/k` selects team members (alongside orphan subagents)
- **Right panel**: task list (pending/in_progress/completed) when team member selected; transcript preview when subagent selected; stats when nothing selected

### Layout

```
━━━ ⠋ CLAUDE AGENTS  2 teams · 3 sessions ━━━━━━━━━━━━━━━━━
 TEAMS (my-project · 4 tasks  2✓ 1● 1○)
 ●   3m  researcher   abc12
 └─  1m  implementer  def45    ← j/k selectable

 SESSIONS (1 running)
 ●   5m  ghi789  fix the login bug

━━━ HISTORY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Right panel (team member selected):
 abc12 · my-project/researcher · 3m
 ──────────────────────────────────
 ✓  Build API endpoints
 ●  Write unit tests
 ○  Update docs
```
