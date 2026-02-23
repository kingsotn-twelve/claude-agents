# Tool Deep-Dive + Error Tracking

**Date**: 2026-02-22
**Status**: Draft

## Problem

The dashboard shows tool events in the TREE timeline as one-liners (`Read file: __init__.py`), but the full tool_input and tool_response data is already captured in SQLite. When debugging agent behavior or watching live progress, you can't see *what* a tool was called with or *what* it returned without leaving the dashboard. Tool failures are invisible — no distinction between success and error.

## Goals

1. **Tool call deep-dive**: expand any tool event inline in the TREE timeline to see full input and a smart summary of the response
2. **Error tracking**: capture `PostToolUseFailure` events, show them as red markers in the timeline, and display error details on expand

## Non-goals

- Token/cost monitoring (covered by claude-code-usage-monitor)
- Session-level monitoring features (covered by claude-monitor, claude-code-monitor)
- Agent flow graphs (nice but low daily value)
- Permission event tracking (easy to add later)

## Design

### Feature 1: Tool Call Inline Expansion

**Interaction**: `j/k` navigates tool events in the TREE. `Enter` toggles expand/collapse on the selected tool event.

**Collapsed** (current):
```
│ 05:14:01 │ Read file: __init__.py
│ 05:13:50 │ Run command: "sele
│ 05:13:38 │ Run command: kin
```

**Expanded** (selected tool event):
```
│ 05:14:01 │ Read file: __init__.py
│ 05:13:50 ┃ Run command: "sele                          89ms
│          ┃ ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
│          ┃  command: "select * from tool_event limit 5"
│          ┃  → 5 rows returned
│          ┃    id=142 session_id=ca9566 tool_name=Read
│          ┃    id=141 session_id=ca9566 tool_name=Grep
│          ┃    ...
│          ┃ ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
│ 05:13:38 │ Run command: kin
```

Visual indicators:
- `┃` bright connector on expanded event (vs `│` dim on collapsed)
- `╌╌╌` dotted separator before/after expanded content
- Duration displayed right-aligned with color: green (<1s), yellow (<5s), red (>5s)
- Expanded content indented under the tool event line

**Smart summary** — parse response by tool type:
- **Read**: first 3 + last 2 lines of file content, total line count
- **Bash**: exit code + last 8 lines of output
- **Grep**: match count + top 5 matches with file:line
- **Edit**: success/fail + old→new preview (first 2 lines of each)
- **Write**: success/fail + file path + byte count
- **Glob**: file count + first 5 matches
- **WebFetch/WebSearch**: result count + first 3 titles/URLs
- **Task**: subagent_type + description
- **Default**: raw JSON truncated to 8 lines

**Input display**: show all key-value pairs from tool_input, one per line, values truncated to fit panel width.

### Feature 2: Error Tracking

**New hook**: `PostToolUseFailure` — fires when a tool call fails.

**DB changes**: add two columns to `tool_event`:
```sql
ALTER TABLE tool_event ADD COLUMN is_error INTEGER DEFAULT 0;
ALTER TABLE tool_event ADD COLUMN error_message TEXT;
```

**Handler**: `handle_post_tool_use_failure(data)` — match by `tool_use_id`, set `is_error=1`, store error message.

**Timeline display**:
```
│ 05:14:01 │ Read file: __init__.py
│ 05:13:50 ✗ Bash: npm test                             4.2s
│ 05:13:38 │ Run command: kin
```

Red `✗` replaces `│` for failed tool calls. Entire line rendered in RED color pair.

**Expanded error**:
```
│ 05:13:50 ✗ Bash: npm test                             4.2s
│          ✗ ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
│          ✗  command: "npm test"
│          ✗  ERROR
│          ✗  Command exited with non-zero status code 1
│          ✗  FAIL src/auth.test.ts
│          ✗    ● login should validate token
│          ✗    Expected: 200, Received: 401
│          ✗ ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
```

Error content rendered in RED. Shows input first, then error message.

**STATS panel**: add ERRORS section showing error counts by tool name, same bar chart format as existing TOOLS section.

### Keyboard Navigation

No new keys — nests into existing model:

| Context | j/k | Enter | Esc |
|---------|-----|-------|-----|
| Left panel (sessions) | Select session | Focus right panel | Deselect |
| Right panel (TREE) | Select tool event | Expand/collapse tool | Back to left panel |
| Expanded tool event | Scroll within expanded content | Collapse | Collapse |

### Hook Registration Changes

Add to `_ccnotify.py` valid events list:
```python
valid = [..., "PostToolUseFailure"]
```

Add to setup output:
```
"PostToolUseFailure": [{"matcher": "", "hooks": [{"type": "command", "command": "... PostToolUseFailure"}]}]
```

### DB Migration

Auto-migration in `_refresh_data()` — same pattern as existing `pid` column migration:
```python
for col, ctype in [("is_error", "INTEGER DEFAULT 0"), ("error_message", "TEXT")]:
    try:
        conn.execute(f"ALTER TABLE tool_event ADD COLUMN {col} {ctype}")
    except sqlite3.OperationalError:
        pass
```

## Implementation Order

1. **PostToolUseFailure handler** — new handler in _ccnotify.py, DB migration, hook registration
2. **Error markers in TREE** — red `✗` for is_error rows, include is_error in queries
3. **Tool event selection in TREE** — j/k navigates tool events, visual selection indicator
4. **Inline expansion** — Enter toggles expand, render input + smart summary
5. **Smart response summaries** — per-tool-type parsers
6. **Duration color coding** — green/yellow/red thresholds
7. **ERRORS in STATS** — query error counts, render section
