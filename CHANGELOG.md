# Changelog

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
