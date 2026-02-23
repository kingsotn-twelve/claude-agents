# The Alive Console — Design Document

**Date**: 2026-02-20
**Status**: Approved
**Inspiration**: Black Mirror (Bandersnatch, Plaything), Severance (Lumon MDR), Sigil/Conway (web4.ai)

---

## Vision

The agent-top dashboard is not a monitoring tool. It is a living thing.

Your agents are alive — they spawn, work, struggle, finish, and die. The dashboard's job is to surface that real vitality, not paint cosmetic life on top of dead data. The console is how you tend to them.

This design document describes two additions:
1. **The Alive Layer** — micro-animations driven by real agent telemetry
2. **The Console** — a persistent bottom panel for natural language interaction with your agent ecosystem

---

## Design DNA (repo-wide)

These are the aesthetic and philosophical principles that govern the entire dashboard, not just the new features.

### Aesthetic Inspirations

**Severance (Lumon MDR)**: Deep navy void. Data floating in darkness. Cold blues. Corporate monospace. Perlin-noise micro-movements on numbers. CRT warmth on HD screens. Enormous negative space. Deliberate, slow tempo.

**Black Mirror: Bandersnatch**: ZX Spectrum palette — cyan, white, black. Hard-cut transitions (no smooth fades, snap to new state). Blinking block cursor. Character-by-character text rendering. The feeling of typing into something that's listening.

**Black Mirror: Plaything**: Warm pixel-art creatures. The Tamagotchi effect — care-taking creates obligation. Population growth creates density. Visible consequences of neglect. The addiction loop: spawn → need → tend → thrive → more spawn → more need.

**Sigil/Conway (web4.ai)**: Real stakes, not cosmetic life. Agents that die if they can't sustain themselves. The heartbeat daemon as a real process. SOUL.md as self-authored identity. Aliveness through genuine fragility.

### Core Principles

1. **Real vitality, not fake animation.** Every visual effect must be driven by real data. The sparkline is an EKG synced to actual tool events, not a decorative loop. Dimming reflects real neglect (you stopped paying attention), not a timer.

2. **Constraint creates trust.** The console has a strict whitelist of what it can do. Limitation is a feature. The fewer things it can do, the more you trust what it does do.

3. **Simple verbs, deep weight.** The simpler the interaction (type a question, read the answer), the more emotional bandwidth is available for the content. No UI chrome competing for attention.

4. **The interface is alive through subtlety.** Breathing borders. Blinking cursors at heartbeat rhythm. One-frame character flickers. You'd only notice if you stared. The life is subliminal.

5. **Care-taking as the core verb.** You don't "monitor" agents. You tend to them. The dashboard rewards attention with clarity and punishes neglect with obscurity.

6. **Hard cuts, not smooth transitions.** State changes snap instantly (Bandersnatch influence). No CSS-style easing. Things appear, things disappear. The abruptness creates visual punctuation.

---

## Part 1: The Alive Layer

Applied to ALL panels, not just the console. This is a global system.

### 1.1 Breathing Borders

Panel borders pulse between dim and slightly-less-dim on a slow cycle (3-4 seconds). The cycle speed is proportional to agent activity:
- High activity (many tool events/sec) → faster breathing (~2s cycle)
- Normal activity → default (~3.5s cycle)
- No activity → very slow breathing (~6s cycle), approaching flatline
- Dead/completed → static dim, no pulse

Implementation: modulate the border color pair's brightness based on a sine wave, where the frequency is derived from the `activity` bucket rate.

### 1.2 Heartbeat Cursor

A persistent blinking cursor in the console prompt area. Blink rate tracks system-wide agent activity:
- Many agents active → ~72 BPM (833ms interval, human resting heart rate)
- Few agents → ~50 BPM (1200ms)
- No agents → ~30 BPM (2000ms), barely alive
- All agents dead → cursor goes solid, stops blinking

### 1.3 Text Shimmer

Random individual characters in the dashboard dim for exactly one frame, then restore. Frequency: ~2-3 characters per second across the entire screen. Gives the CRT loose-connection feel. Never touches the currently selected row.

### 1.4 Warmth Gradient

Active sessions render in warm colors (yellow/green sparklines, bright text). As sessions age without new tool events, they cool — transitioning from yellow → white → dim cyan → grey. This is a continuous gradient based on `time_since_last_tool_event`.

### 1.5 Death Animation

When an agent stops (SubagentStop event):
- **Success**: Brief green flash on the agent's row (1 frame), then normal transition to HISTORY
- **Failure**: Border of the row flickers red for 2-3 frames, then row greys out slowly over ~5 frames (not instant — like warmth leaving)
- **Orphan**: Tree connector character (`├` or `└`) changes to a broken connector (`╌`) before the orphan reaper moves it

### 1.6 Idle Drift

When the dashboard has been idle (no keyboard input) for 30+ seconds, numbers in the STATS panel occasionally shift by ±1 for a single frame, then snap back. Severance-style Perlin noise. Very rare — once every 5-10 seconds. Creates the subliminal feeling that the numbers are breathing.

---

## Part 2: The Console

### 2.1 Placement

A new 5th panel at the bottom of the screen. Always visible. Height: 5-8 rows (configurable, default 6). Contains:
- Row 1: Box border with title `CONSOLE`
- Row 2: Prompt line with blinking cursor: `> _`
- Rows 3-N: Response area (scrollable)
- Last row: Box border (bottom)

The console takes horizontal space from the full width of the terminal (same as the title bar).

### 2.2 Input Model

User presses `/` or `Tab` to focus the console (cursor moves to prompt line). Types natural language. Presses Enter to submit. Presses Esc to unfocus and return to panel navigation.

The prompt supports basic line editing (backspace, left/right arrow, home/end). No multi-line input — single line only.

### 2.3 Processing Pipeline

```
User types query
    ↓
Console parses intent locally (fast-path for known patterns)
    ↓
If no local match → send to Claude API with:
  - System prompt (constrained to dashboard domain)
  - Current dashboard state (active sessions, agents, recent events)
  - User query
    ↓
Claude returns structured JSON:
  {
    "plan": [
      {"action": "sql", "query": "SELECT ..."},
      {"action": "shell", "cmd": "git log --oneline -5"},
      {"action": "read", "path": "/path/to/file"}
    ],
    "render": {
      "widget": "table",
      "title": "Recent Errors"
    }
  }
    ↓
Dashboard executes plan:
  - Read actions: auto-execute
  - Write actions: show confirmation prompt
    ↓
Results rendered in response area
```

### 2.4 Fast Paths (No API Call)

Common queries that can be answered directly from cached dashboard data:

| Pattern | Action |
|---|---|
| `agents` / `sessions` | Show count + list of active |
| `tools` | Show tool usage stats from cache |
| `history` | Show recent completed items |
| `agent <name/id>` | Show detail for specific agent |
| `clear` | Clear console response area |
| `help` | Show available commands |

These render instantly with no API latency.

### 2.5 Claude API Integration

For queries that require interpretation, the console calls the Claude API.

**System prompt** (condensed):
```
You are the console for a terminal dashboard monitoring Claude Code agents.
You have access to: SQLite database (sessions, agents, tool events, teams),
file system (transcripts, configs), and shell commands (git, system info).

Return a JSON plan with actions to execute and a render specification.

Available actions: sql, shell, read_file, read_transcript
Available widgets: table, bar_chart, sparkline, kv_card, text

Constraints:
- Never modify files, databases, or system state without explicit user request
- Never access credentials, .env files, or secrets
- Never make network requests to external services
- Keep shell commands read-only (no rm, mv, write operations) unless confirmed
```

**Render specification format:**
```json
{
  "widget": "table",
  "title": "string",
  "columns": ["col1", "col2"],
  "rows": [["val1", "val2"]],
  "highlight": {"column": 0, "value": "error", "color": "red"}
}
```

Widget types:
- `table`: columns + rows, optional highlighting
- `bar_chart`: labels + values, rendered with Unicode blocks (▁▂▃▄▅▆▇█)
- `sparkline`: array of values, rendered with braille characters
- `kv_card`: key-value pairs in a bordered box
- `text`: plain text, rendered character-by-character

### 2.6 Character-by-Character Rendering

All text responses render character-by-character at ~60 chars/sec. This creates the feeling of someone typing a response to you. Implementation:
- Queue the full response string
- In the frame loop, advance the render cursor by N characters per frame (at 10 FPS = 6 chars/frame)
- Tables and charts snap into place fully formed after the title types out (hard cut)

### 2.7 Proactive Surfacing

The console can display messages unprompted when agent telemetry warrants it:
- Agent stuck (no tool events for 2+ minutes while running) → `agent-name seems stuck (no activity for 2m)`
- Agent errored → `agent-name hit an error: <tool_name> failed`
- Session completed → `session abc123 finished (3m, 12 tools)`

These messages appear character-by-character in the response area, dimmed (not bright — they're ambient, not alerts). They scroll up as new messages arrive.

### 2.8 Write Confirmation

When the console needs to execute a write operation (kill process, write file, git command), it shows:

```
> kill the stalled explore agent

  This will terminate agent abc123 (explore, running 12m).
  Press Enter to confirm, Esc to cancel.
```

No timer. No forced choice. Just a clear description of what will happen and a confirmation gate.

### 2.9 Session Memory

The console tracks queries within a session (not persisted across restarts). Benefits:
- Up-arrow recalls previous queries
- Context window for Claude API calls includes recent Q&A pairs
- Enables follow-up queries: "what about last week?" after "show tool usage today"

---

## Part 3: Architecture

### 3.1 Dependencies

New dependency: `anthropic` Python SDK (for Claude API calls). This is the first external dependency beyond stdlib. Alternatively, use raw `urllib` to avoid the dependency — keep the zero-dependency philosophy.

API key: read from `ANTHROPIC_API_KEY` environment variable. If not set, console operates in local-only mode (fast paths only, no Claude interpretation).

### 3.2 Code Organization

Given the current monolithic structure (1,847 lines in one file), the console adds:
- `ConsoleState` dict in the global state (prompt text, response buffer, render queue, history)
- `draw_console()` function called from `draw()` after all other panels
- `handle_console_input()` function for keystroke processing
- `execute_plan()` function for running Claude's action plans
- `render_widget()` function for turning structured data into curses output

Estimated addition: ~400-500 lines.

### 3.3 Frame Loop Integration

The alive layer hooks into the existing 100ms frame loop:
- Breathing borders: compute sine wave phase each frame, apply to `draw_box()` border_attr
- Text shimmer: randomly select 0-1 screen positions per frame to dim
- Heartbeat cursor: toggle cursor visibility based on blink timer
- Warmth gradient: compute per-session color based on `time_since_last_tool_event`
- Character-by-character: advance render cursor by N chars per frame
- Proactive surfacing: check agent telemetry every data refresh (~2s) for stuck/error conditions

### 3.4 Console Layout Calculation

The console panel reduces the available height for the left panel stack. Current layout:
```
Title bar:     2 rows
TEAMS:         variable
SESSIONS:      variable
HISTORY:       variable
STATS:         variable
```

New layout:
```
Title bar:     2 rows
TEAMS:         variable
SESSIONS:      variable
HISTORY:       variable (may shrink)
STATS:         variable (may shrink)
CONSOLE:       6 rows (fixed)
```

When terminal height is small (<30 rows), HISTORY and STATS panels shrink first to preserve SESSIONS and CONSOLE.

---

## Success Criteria

1. **The dashboard feels alive when you look at it.** Borders breathe. Cursor blinks. Characters shimmer. You can't quite tell if the screen is moving, but something feels present.

2. **The console answers real questions.** "What broke today?" returns actual errors from the database. "Show me git log" returns real git output. No hallucinated or mocked data.

3. **Tending feels rewarding.** Checking on an agent (scrolling to it, querying about it) makes its representation clearer and brighter. Neglect makes things fade. The dashboard reflects your attention.

4. **The addiction loop works.** After a week of use, closing the dashboard feels like leaving something alive alone. Not because of manipulation — because you've been tending to it and it has become part of your workflow rhythm.

5. **Zero external dependencies (stretch).** If we can do Claude API calls with raw urllib/http.client instead of the anthropic SDK, we maintain the zero-dependency philosophy.
