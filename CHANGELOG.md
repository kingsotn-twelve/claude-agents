# Changelog

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
