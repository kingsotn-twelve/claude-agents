# Alive Console — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a living "Alive Layer" of micro-animations driven by real agent telemetry, plus a persistent Console panel for natural language queries about agent state.

**Architecture:** Two independent feature tracks that share the same frame loop. Track A (Alive Layer) modifies existing render functions — `draw_box()`, session rows, stats rows — to incorporate time-based effects (sine wave borders, warmth gradients, shimmer). Track B (Console) adds a new bottom panel with input handling, Claude API integration via raw `urllib`, and a character-by-character text renderer. Both tracks hook into the existing 200ms frame loop and 2s data refresh cycle.

**Tech Stack:** Python 3 stdlib only (curses, math, urllib.request, json, threading). Zero external dependencies — Claude API calls use raw HTTP.

---

## Track A: Alive Layer

### Task 1: Add `math` import and alive-layer state fields

**Files:**
- Modify: `agent-top:8-18` (imports)
- Modify: `agent-top:2109-2111` (state dict)

**Step 1: Add math import**

Add `import math` after `import json` at line 13:

```python
import math
```

**Step 2: Add alive-layer fields to state dict**

In `main()` at line 2109, extend the state dict:

```python
state: dict = {"selected": -1, "visible_items": [], "status_msg": "", "status_until": 0.0,
               "stats_range": 2, "game_of_life": game_of_life, "focus": "left", "detail_scroll": 0,
               "viz_mode": 0,
               # Alive layer
               "last_input_time": time.time(),
               "shimmer_positions": [],  # [(row, col, frame_added)]
               }
```

**Step 3: Run to verify no crash**

Run: `python3 agent-top --help` (or just launch briefly and quit with `q`)
Expected: Dashboard starts without errors.

**Step 4: Commit**

```bash
git add agent-top
git commit -m "feat: add math import and alive-layer state fields"
```

---

### Task 2: Breathing borders — dynamic `draw_box()` brightness

**Files:**
- Modify: `agent-top:994-1011` (`draw_box()` function)
- Modify: `agent-top:91-128` (`init_colors()` — add breathing color pairs)

**Step 1: Add breathing color pairs in `init_colors()`**

After the existing SEL color pairs (line ~120), add dim-variant pairs for breathing borders. We need two brightness levels for the border: DIM (existing, base) and a slightly brighter "inhale" state.

```python
    # Breathing border colors (pair 21-22: slightly brighter borders)
    try:
        curses.init_pair(21, 240, -1)  # dim border (exhale) — slightly dimmer than DIM
        curses.init_pair(22, 245, -1)  # bright border (inhale) — slightly brighter than DIM
    except curses.error:
        pass
```

Add globals after the SEL globals:

```python
BORDER_DIM = 0
BORDER_BRIGHT = 0
```

Initialize them in `init_colors()`:

```python
    global BORDER_DIM, BORDER_BRIGHT
    try:
        BORDER_DIM = curses.color_pair(21)
        BORDER_BRIGHT = curses.color_pair(22)
    except curses.error:
        BORDER_DIM = DIM
        BORDER_BRIGHT = DIM
```

**Step 2: Add `breathing_attr()` helper function**

Place this right after the `sparkline()` function (after line 575):

```python
def breathing_attr(frame: int, activity_rate: float = 0.0) -> int:
    """Return a border attr that pulses between dim and bright based on activity.

    activity_rate: tool events per second (0.0 = idle, >1.0 = busy).
    Returns a curses color pair that oscillates via sine wave.
    """
    if activity_rate <= 0:
        # Very slow breathing when idle (6s cycle = ~30 frames at 5fps)
        cycle_frames = 30
    elif activity_rate < 0.5:
        # Normal breathing (3.5s cycle = ~17 frames)
        cycle_frames = 17
    else:
        # Fast breathing when busy (2s cycle = ~10 frames)
        cycle_frames = 10

    phase = math.sin(2 * math.pi * frame / cycle_frames)
    # phase ranges -1 to 1; map to 0 or 1 (two brightness levels)
    if phase > 0:
        return BORDER_BRIGHT
    return BORDER_DIM
```

**Step 3: Wire breathing into `draw()` — compute activity rate and pass to draw_box()**

In `draw()` around line 1370, after cache unpacking, compute a global activity rate:

```python
    # Alive layer: global activity rate (tool events per second across all sessions)
    total_activity = sum(sum(b) for b in activity.values())  # total tool events in last 60s
    activity_rate = total_activity / 60.0 if total_activity else 0.0
    border_attr = breathing_attr(frame, activity_rate)
```

Then replace every `draw_box()` call in the draw function that currently passes no `border_attr` or passes `DIM` — change them to pass `border_attr` instead. The key draw_box calls are:
- TEAMS panel (search for `draw_box(stdscr,` with "TEAMS")
- SESSIONS panel
- HISTORY panel
- STATS panel

Each call should change from:
```python
draw_box(stdscr, y, x, h, w, title)
```
to:
```python
draw_box(stdscr, y, x, h, w, title, border_attr=border_attr)
```

**Step 4: Visual verification**

Run the dashboard. Borders should subtly pulse between two brightness levels. If no agents are running, the pulse should be very slow (~6s). If agents are active, faster.

**Step 5: Commit**

```bash
git add agent-top
git commit -m "feat: breathing borders driven by agent activity rate"
```

---

### Task 3: Heartbeat cursor in footer area

**Files:**
- Modify: `agent-top:2081-2094` (footer rendering)

**Step 1: Add heartbeat cursor to footer**

In the footer section (line 2081), before the existing footer rendering, add a heartbeat dot:

```python
    # -- Heartbeat cursor --
    n_active = len(r_agents) + len(active)
    if n_active > 3:
        blink_interval = 4    # ~800ms at 200ms/frame (72 BPM)
    elif n_active > 0:
        blink_interval = 6    # ~1200ms (50 BPM)
    else:
        blink_interval = 10   # ~2000ms (30 BPM)
    heartbeat_visible = (frame % blink_interval) < (blink_interval // 2)
    heartbeat_char = "●" if heartbeat_visible else "○"
    heartbeat_color = GREEN if n_active > 0 else DIM
    safe_add(stdscr, h - 1, w - 3, heartbeat_char, w, heartbeat_color)
```

This places a pulsing dot in the bottom-right corner of the screen.

**Step 2: Visual verification**

Run dashboard. Bottom-right should show a blinking dot. Speed varies with agent count.

**Step 3: Commit**

```bash
git add agent-top
git commit -m "feat: heartbeat cursor — blinking dot synced to agent activity"
```

---

### Task 4: Text shimmer — CRT flicker effect

**Files:**
- Modify: `agent-top:1370` area (in `draw()`, at the end before `stdscr.refresh()`)

**Step 1: Add shimmer logic at end of draw(), before stdscr.refresh()**

Right before `stdscr.refresh()` at line 2094, insert:

```python
    # -- Text shimmer (CRT flicker) --
    # Dim 1-2 random characters per frame, skip selected row and footer
    if frame % 3 == 0:  # ~1.6 chars/sec at 5fps
        sel_row = -1
        if 0 <= state.get("selected", -1) < len(visible_items):
            # Don't shimmer the selected row — find its screen position
            # (approximate: we don't track exact row, so skip shimmer on small terminals)
            pass
        shimmer_row = random.randint(content_top + 1, max(content_top + 2, h - 3))
        shimmer_col = random.randint(2, max(3, lw - 3))
        try:
            # Read existing char, redraw it dimmed for one frame
            existing = stdscr.inch(shimmer_row, shimmer_col)
            char_only = existing & 0xFF
            if char_only > 32:  # only shimmer visible characters
                stdscr.addch(shimmer_row, shimmer_col, char_only, DIM | curses.A_DIM)
        except curses.error:
            pass
```

**Step 2: Visual verification**

Run dashboard. Occasionally, a single character should dim for one frame then restore (next frame redraws it normally). Very subtle — you have to stare to notice.

**Step 3: Commit**

```bash
git add agent-top
git commit -m "feat: text shimmer — subtle CRT flicker effect"
```

---

### Task 5: Warmth gradient — session color based on recency

**Files:**
- Modify: `agent-top:91-128` (`init_colors()` — add warmth color pairs)
- Modify: `agent-top` session rendering section (~line 1551-1640)

**Step 1: Add warmth color helper**

After `breathing_attr()`, add:

```python
def warmth_attr(last_tool_time_str: str, bold: bool = True) -> int:
    """Return a color attr based on how recently the session had tool activity.

    Recent activity = warm (YELLOW). Aging = WHITE. Cold = DIM.
    """
    if not last_tool_time_str:
        return DIM
    try:
        last = datetime.fromisoformat(last_tool_time_str).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last).total_seconds()
    except Exception:
        return DIM

    if age < 10:
        return YELLOW  # hot — active right now
    elif age < 60:
        return GREEN   # warm — active recently
    elif age < 300:
        return WHITE   # cooling — been a few minutes
    elif age < 600:
        return CYAN    # cool
    else:
        return DIM     # cold — stale
```

**Step 2: Apply warmth to session sparklines**

In the session rendering section, where sparklines are drawn for sessions, use `warmth_attr()` to color the sparkline based on the most recent tool event time.

Find where sparklines are rendered for sessions (search for `sparkline(` calls in the session section). The sparkline text is currently drawn with a static color. Replace that color with:

```python
# Get most recent tool event time for warmth
session_tools = cache.get("session_tools", {}).get(sid, [])
last_tool_ts = session_tools[-1]["created_at"] if session_tools else ""
spark_color = warmth_attr(last_tool_ts)
```

**Step 3: Visual verification**

Run dashboard with active agents. Active session sparklines should be yellow/green. Sessions that haven't had tool events recently should cool to white/cyan/dim.

**Step 4: Commit**

```bash
git add agent-top
git commit -m "feat: warmth gradient — session sparklines color by recency"
```

---

### Task 6: Idle drift — Severance-style number breathing in STATS

**Files:**
- Modify: `agent-top` STATS panel rendering (~line 1786-1891)

**Step 1: Add idle drift to STATS numbers**

In the STATS panel rendering, where count numbers are drawn (the `cnt` values for top agents and tools), add drift logic:

```python
    # Idle drift: when no keyboard input for 30s, numbers occasionally wobble ±1
    idle_secs = time.time() - state.get("last_input_time", time.time())
    drift_active = idle_secs > 30
```

Then in the number rendering, when `drift_active` is True:

```python
    if drift_active and frame % 40 == 0 and random.random() < 0.3:
        # One random stat drifts by ±1 for a single frame
        display_cnt = cnt + random.choice([-1, 1])
    else:
        display_cnt = cnt
```

**Step 2: Update `last_input_time` on any keypress**

In the main loop (line 2120), after `ch = stdscr.getch()`, add:

```python
        if ch != -1:
            state["last_input_time"] = time.time()
```

**Step 3: Visual verification**

Run dashboard. Wait 30+ seconds without pressing anything. Occasionally, a stat number should flicker by ±1 for a single frame.

**Step 4: Commit**

```bash
git add agent-top
git commit -m "feat: idle drift — Severance-style number breathing in STATS panel"
```

---

## Track B: Console Panel

### Task 7: Console panel layout and empty rendering

**Files:**
- Modify: `agent-top:2109-2111` (state dict — add console fields)
- Modify: `agent-top:1459-1488` (panel height calculation)
- Modify: `agent-top:2081-2094` (draw console before footer)

**Step 1: Add console state fields**

Extend the state dict in `main()`:

```python
               # Console
               "console_focus": False,
               "console_input": "",
               "console_cursor": 0,
               "console_lines": [],     # list of {"text": str, "attr": int, "typed": bool}
               "console_scroll": 0,
               "console_history": [],   # previous queries for up-arrow recall
               "console_history_idx": -1,
               "console_typing_queue": None,  # {"text": str, "pos": int, "attr": int}
```

**Step 2: Add CONSOLE_H constant**

Near the top constants (after line 28):

```python
CONSOLE_H = 6  # fixed height of console panel
```

**Step 3: Modify panel height calculation to reserve space for console**

In the layout calculation section (line 1481), change:

```python
    remaining = max(6, h - content_top - teams_h - sess_h - 1)
```

to:

```python
    console_h = CONSOLE_H
    remaining = max(6, h - content_top - teams_h - sess_h - console_h - 1)
```

And similarly for the idle case at line 1488:

```python
        remaining = max(6, h - content_top - sess_h - console_h - 1)
```

**Step 4: Add `draw_console()` function**

Place after `draw_box()` (after line 1011):

```python
def draw_console(stdscr, frame: int, state: dict, y: int, w: int, cache: dict):
    """Draw the CONSOLE panel at the bottom of the screen."""
    ch = CONSOLE_H
    if ch < 3:
        return

    # Breathing border for console too
    total_activity = sum(sum(b) for b in cache.get("activity", {}).values())
    activity_rate = total_activity / 60.0 if total_activity else 0.0
    ba = breathing_attr(frame, activity_rate)

    draw_box(stdscr, y, 0, ch, w, "CONSOLE", border_attr=ba)

    # Prompt line
    prompt_y = y + 1
    prompt_x = 2
    prefix = "> "
    safe_add(stdscr, prompt_y, prompt_x, prefix, w - 1, CYAN)

    input_text = state.get("console_input", "")
    safe_add(stdscr, prompt_y, prompt_x + len(prefix), input_text, w - 3, WHITE)

    # Blinking cursor
    if state.get("console_focus"):
        cursor_x = prompt_x + len(prefix) + state.get("console_cursor", len(input_text))
        # Heartbeat-rate blink
        n_active = len(cache.get("r_agents", []))
        blink_interval = 4 if n_active > 3 else (6 if n_active > 0 else 10)
        if (frame % blink_interval) < (blink_interval // 2):
            safe_add(stdscr, prompt_y, min(cursor_x, w - 3), "█", w - 1, CYAN)

    # Response lines (scrollable)
    lines = state.get("console_lines", [])
    typing_q = state.get("console_typing_queue")
    max_lines = ch - 3  # rows available for response (box top + prompt + box bottom)
    start = max(0, len(lines) - max_lines - state.get("console_scroll", 0))
    for i, line in enumerate(lines[start:start + max_lines]):
        line_y = y + 2 + i
        text = line.get("text", "")

        # Character-by-character rendering for typing queue
        if typing_q and i == len(lines) - start - 1:
            pos = typing_q.get("pos", 0)
            text = text[:pos]

        attr = line.get("attr", DIM)
        safe_add(stdscr, line_y, 2, text, w - 2, attr)
```

**Step 5: Call `draw_console()` from `draw()`**

In `draw()`, right before the footer section (before line 2081 "-- Footer --"), add:

```python
    # -- Console panel (bottom, full width) --
    console_y = h - CONSOLE_H - 1  # -1 for footer
    draw_console(stdscr, frame, state, console_y, w if not split else lw, cache)
```

Note: Use `lw` (left panel width) when split so it doesn't overlap the right panel. Or use full width `w` — design choice based on how it looks.

**Step 6: Visual verification**

Run dashboard. A "CONSOLE" box should appear at the bottom with `> ` prompt inside. No input handling yet.

**Step 7: Commit**

```bash
git add agent-top
git commit -m "feat: console panel — empty layout with breathing borders and blinking cursor"
```

---

### Task 8: Console input handling — typing, editing, focus

**Files:**
- Modify: `agent-top:2120-2222` (keyboard input handling in main loop)

**Step 1: Add console focus toggle**

In the keyboard handling, add `/` key to toggle console focus:

```python
        elif ch == ord("/"):
            state["console_focus"] = not state["console_focus"]
            if state["console_focus"]:
                state["console_cursor"] = len(state.get("console_input", ""))
```

Modify the Esc handler to also unfocus console:

```python
        elif ch == 27:  # Esc
            if state.get("console_focus"):
                state["console_focus"] = False
            elif state["focus"] == "right":
                ...
```

**Step 2: Add text input handling when console is focused**

After the existing keybinding handlers, add a console input block that runs when `console_focus` is True. This should be checked early (before the normal j/k/h/l handlers) so that keys go to the console when focused:

```python
        if state.get("console_focus") and ch != -1:
            if ch in (10, 13, curses.KEY_ENTER):
                # Submit query
                query = state["console_input"].strip()
                if query:
                    state["console_history"].append(query)
                    state["console_history_idx"] = -1
                    _handle_console_query(query, state, cache)
                    state["console_input"] = ""
                    state["console_cursor"] = 0
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                pos = state["console_cursor"]
                if pos > 0:
                    inp = state["console_input"]
                    state["console_input"] = inp[:pos - 1] + inp[pos:]
                    state["console_cursor"] = pos - 1
            elif ch == curses.KEY_LEFT:
                state["console_cursor"] = max(0, state["console_cursor"] - 1)
            elif ch == curses.KEY_RIGHT:
                state["console_cursor"] = min(len(state["console_input"]), state["console_cursor"] + 1)
            elif ch == curses.KEY_UP:
                # Recall previous query
                hist = state["console_history"]
                if hist:
                    idx = state.get("console_history_idx", -1)
                    idx = max(0, (len(hist) - 1 if idx == -1 else idx - 1))
                    state["console_history_idx"] = idx
                    state["console_input"] = hist[idx]
                    state["console_cursor"] = len(hist[idx])
            elif ch == curses.KEY_DOWN:
                hist = state["console_history"]
                idx = state.get("console_history_idx", -1)
                if idx >= 0 and idx < len(hist) - 1:
                    idx += 1
                    state["console_history_idx"] = idx
                    state["console_input"] = hist[idx]
                    state["console_cursor"] = len(hist[idx])
                else:
                    state["console_history_idx"] = -1
                    state["console_input"] = ""
                    state["console_cursor"] = 0
            elif 32 <= ch <= 126:
                # Regular character
                pos = state["console_cursor"]
                inp = state["console_input"]
                state["console_input"] = inp[:pos] + chr(ch) + inp[pos:]
                state["console_cursor"] = pos + 1
            continue  # consume the key — don't fall through to panel nav
```

Important: This block must be placed at the TOP of the key handling, before `j/k/h/l/q` handlers, and must `continue` to prevent fallthrough.

**Step 3: Visual verification**

Run dashboard. Press `/` to focus console. Type text — it should appear after `> `. Backspace, arrows, up-arrow for history should work.

**Step 4: Commit**

```bash
git add agent-top
git commit -m "feat: console input — typing, editing, history recall, focus toggle"
```

---

### Task 9: Console fast paths — local query handling

**Files:**
- Modify: `agent-top` (add `_handle_console_query()` function)

**Step 1: Add `_handle_console_query()` function**

Place after `draw_console()`:

```python
def _handle_console_query(query: str, state: dict, cache: dict):
    """Handle a console query. Try fast paths first, then Claude API."""
    q = query.lower().strip()

    def add_line(text, attr=WHITE):
        state["console_lines"].append({"text": text, "attr": attr})

    def add_typed(text, attr=WHITE):
        """Add a line that will render character-by-character."""
        state["console_lines"].append({"text": text, "attr": attr, "typed": True})
        state["console_typing_queue"] = {"text": text, "pos": 0, "attr": attr}

    # Fast path: clear
    if q == "clear":
        state["console_lines"] = []
        state["console_typing_queue"] = None
        return

    # Fast path: help
    if q in ("help", "?"):
        add_line("commands: agents, sessions, tools, history, clear, help", DIM)
        add_line("or type any question (needs ANTHROPIC_API_KEY)", DIM)
        return

    # Fast path: agents / sessions
    if q in ("agents", "sessions"):
        r_agents = cache.get("r_agents", [])
        active = cache.get("active_all", [])
        add_line(f"{len(active)} sessions, {len(r_agents)} agents running", CYAN)
        for a in r_agents[:8]:
            atype = (a.get("agent_type") or "?")[:15]
            dur = fmt_dur(a["started_at"])
            add_line(f"  {atype:<15} {dur:>6}  {short_id(a['agent_id'])}", DIM)
        return

    # Fast path: tools
    if q == "tools":
        top = cache.get("data", {}).get("top_tools", [])
        if top:
            add_line("top tools:", CYAN)
            for t in top[:6]:
                name = t["tool_name"]
                cnt = t["cnt"]
                add_line(f"  {name:<20} {cnt:>4}", DIM)
        else:
            add_line("no tool data", DIM)
        return

    # Fast path: history
    if q == "history":
        recent = cache.get("recent", [])
        if recent:
            add_line(f"{len(recent)} recent completions:", CYAN)
            for r in recent[:6]:
                prompt = short_prompt(r.get("prompt", ""), 30)
                ts = fmt_time(r["created_at"]) if r.get("created_at") else ""
                add_line(f"  {ts}  {prompt}", DIM)
        else:
            add_line("no history", DIM)
        return

    # No fast path match — try Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        add_line("no ANTHROPIC_API_KEY set — local commands only", RED)
        add_line("try: agents, sessions, tools, history, help", DIM)
        return

    # Queue for async API call
    add_line("thinking...", DIM)
    _console_api_call(query, state, cache, api_key)
```

**Step 2: Visual verification**

Run dashboard. Press `/`, type `help`, press Enter. Should show command list. Try `agents`, `tools`, `history`, `clear`.

**Step 3: Commit**

```bash
git add agent-top
git commit -m "feat: console fast paths — agents, sessions, tools, history, help, clear"
```

---

### Task 10: Console Claude API integration — raw urllib

**Files:**
- Modify: `agent-top` (add `_console_api_call()` function)
- Modify: `agent-top:8-18` (add `import threading`, `import urllib.request`, `import urllib.error`)

**Step 1: Add imports**

Add at the top with other imports:

```python
import threading
import urllib.request
import urllib.error
```

**Step 2: Add the API call function**

Place after `_handle_console_query()`:

```python
CONSOLE_SYSTEM_PROMPT = """You are the console for a terminal dashboard monitoring Claude Code sessions and agents.
You have access to: SQLite database (sessions, agents, tool events, teams), file system (transcripts, configs), and shell commands (read-only: git log, ls, cat, df, etc).

Return ONLY valid JSON with this structure:
{"plan": [{"action": "sql"|"shell"|"read_file", "query"|"cmd"|"path": "..."}], "render": {"widget": "table"|"bar_chart"|"kv_card"|"text", "title": "...", ...}}

Widget specifications:
- table: {"widget":"table","title":"...","columns":["a","b"],"rows":[["x","y"]]}
- bar_chart: {"widget":"bar_chart","title":"...","labels":["a","b"],"values":[1,2]}
- kv_card: {"widget":"kv_card","title":"...","pairs":[["key","val"]]}
- text: {"widget":"text","title":"...","body":"plain text response"}

Available actions:
- sql: query the SQLite DB at {db_path}. Tables: prompt(session_id,prompt,cwd,created_at,stoped_at,lastWaitUserAt,seq), agent(agent_id,agent_type,session_id,cwd,started_at,stopped_at,transcript_path), tool_event(session_id,tool_name,tool_label,created_at), team_session(session_id,team_name,teammate_name,last_seen_at)
- shell: run a read-only shell command (git log, ls, cat, df, uptime, wc, du, etc). NEVER use rm, mv, kill, or write commands.
- read_file: read a file path

Constraints:
- ONLY return JSON. No markdown, no explanation.
- Never modify files, databases, or state
- Never access .env or credentials
- Shell commands must be read-only
- Keep responses concise — the terminal panel is small"""


def _console_api_call(query: str, state: dict, cache: dict, api_key: str):
    """Call Claude API in a background thread and update console_lines when done."""

    def _call():
        try:
            # Build context from cache
            r_agents = cache.get("r_agents", [])
            active = cache.get("active_all", [])
            context = {
                "active_sessions": len(active),
                "running_agents": len(r_agents),
                "agents": [{"type": a.get("agent_type"), "id": a["agent_id"][:7],
                            "duration": fmt_dur(a["started_at"])} for a in r_agents[:10]],
                "recent_history": len(cache.get("recent", [])),
            }

            system_prompt = CONSOLE_SYSTEM_PROMPT.replace("{db_path}", DB_PATH)
            user_msg = f"Dashboard state: {json.dumps(context)}\n\nUser query: {query}"

            body = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_msg}],
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())

            text_content = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text_content += block["text"]

            # Remove "thinking..." line
            if state["console_lines"] and state["console_lines"][-1].get("text") == "thinking...":
                state["console_lines"].pop()

            # Parse JSON response and execute plan
            _execute_console_plan(text_content, state, cache)

        except Exception as e:
            if state["console_lines"] and state["console_lines"][-1].get("text") == "thinking...":
                state["console_lines"].pop()
            state["console_lines"].append({"text": f"error: {str(e)[:60]}", "attr": RED})

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
```

**Step 3: Add plan execution function**

```python
def _execute_console_plan(response_text: str, state: dict, cache: dict):
    """Parse Claude's JSON response, execute the plan, render the widget."""
    def add_line(text, attr=WHITE):
        state["console_lines"].append({"text": text, "attr": attr})

    try:
        # Strip any markdown code fences
        text = response_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        plan = json.loads(text)
    except json.JSONDecodeError:
        # If not valid JSON, just show as text
        for line in response_text.strip().split("\n")[:6]:
            add_line(line[:80], DIM)
        return

    # Execute plan actions and collect results
    results = []
    for action in plan.get("plan", []):
        act_type = action.get("action", "")
        try:
            if act_type == "sql":
                query = action.get("query", "")
                if any(kw in query.upper() for kw in ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE")):
                    results.append("blocked: write query not allowed")
                    continue
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(query).fetchall()]
                conn.close()
                results.append(rows)
            elif act_type == "shell":
                cmd = action.get("cmd", "")
                if any(kw in cmd for kw in ("rm ", "mv ", "kill ", "> ", ">> ", "sudo")):
                    results.append("blocked: write command not allowed")
                    continue
                out = subprocess.check_output(cmd, shell=True, timeout=5, stderr=subprocess.STDOUT)
                results.append(out.decode(errors="replace").strip())
            elif act_type == "read_file":
                path = action.get("path", "")
                with open(os.path.expanduser(path), "r", errors="replace") as f:
                    results.append(f.read(4096))
        except Exception as e:
            results.append(f"error: {e}")

    # Render widget
    render = plan.get("render", {})
    widget = render.get("widget", "text")
    title = render.get("title", "")

    if title:
        add_line(title, CYAN)

    if widget == "table":
        cols = render.get("columns", [])
        rows = render.get("rows", [])
        # If plan returned SQL results, use those
        if results and isinstance(results[0], list) and results[0]:
            if not rows:
                cols = cols or list(results[0][0].keys())
                rows = [[str(r.get(c, "")) for c in cols] for r in results[0]]
        if cols:
            header = "  ".join(f"{c:<15}" for c in cols[:4])
            add_line(header, CYAN)
        for row in rows[:10]:
            line = "  ".join(f"{str(v):<15}" for v in row[:4])
            add_line(line, DIM)

    elif widget == "bar_chart":
        labels = render.get("labels", [])
        values = render.get("values", [])
        if results and isinstance(results[0], list):
            for r in results[0][:8]:
                vals = list(r.values())
                if len(vals) >= 2:
                    labels.append(str(vals[0]))
                    try:
                        values.append(int(vals[-1]))
                    except (ValueError, TypeError):
                        values.append(0)
        mx = max(values) if values else 1
        blocks = "▁▂▃▄▅▆▇█"
        for label, val in zip(labels[:8], values[:8]):
            bar_len = int(val / mx * 8) if mx > 0 else 0
            bar = blocks[min(bar_len, 7)] * 8
            add_line(f"  {bar} {val:>4}  {label[:20]}", DIM)

    elif widget == "kv_card":
        pairs = render.get("pairs", [])
        for k, v in pairs[:8]:
            add_line(f"  {k}: {v}", DIM)

    else:  # text
        body = render.get("body", "")
        if not body and results:
            body = str(results[0]) if results else ""
        for line in body.split("\n")[:8]:
            add_line(f"  {line[:76]}", DIM)
```

**Step 4: Visual verification**

Set `ANTHROPIC_API_KEY` env var. Run dashboard. Press `/`, type "what agents ran today?", press Enter. Should show "thinking...", then results.

Without API key: should show "no ANTHROPIC_API_KEY" message.

**Step 5: Commit**

```bash
git add agent-top
git commit -m "feat: console Claude API — background queries with plan execution and widget rendering"
```

---

### Task 11: Character-by-character typing effect

**Files:**
- Modify: `draw_console()` function
- Modify: `draw()` frame loop

**Step 1: Advance typing queue each frame**

In `draw()`, right before calling `draw_console()`, advance the typing queue:

```python
    # Advance character-by-character typing
    tq = state.get("console_typing_queue")
    if tq and tq["pos"] < len(tq["text"]):
        tq["pos"] += 2  # ~2 chars per frame at 5fps = ~10 chars/sec
    elif tq:
        state["console_typing_queue"] = None
```

**Step 2: Update `draw_console()` to use typing position**

The `draw_console()` function already has the typing queue logic from Task 7. Verify that when `typing_q` is active, only `text[:pos]` is rendered for the last line.

**Step 3: Update `_handle_console_query()` to use typed lines**

For fast-path responses, the first response line should use `add_typed()` instead of `add_line()` to trigger the effect:

```python
    # In fast path handlers, replace the first add_line call with:
    add_typed("5 sessions, 3 agents running", CYAN)
```

Only the first line of each response types out. Subsequent lines appear via hard cut.

**Step 4: Visual verification**

Press `/`, type `agents`. The first line of the response should type out character by character. Remaining lines appear instantly.

**Step 5: Commit**

```bash
git add agent-top
git commit -m "feat: character-by-character typing effect in console responses"
```

---

### Task 12: Proactive surfacing — stuck/completed agent messages

**Files:**
- Modify: `refresh_data()` (line 1016-1035) or the frame loop

**Step 1: Add agent health check on data refresh**

In the frame loop, after `refresh_data()` is called (line 2117), add:

```python
            # Proactive surfacing: check for stuck or newly completed agents
            _check_agent_health(state, cache)
```

**Step 2: Add `_check_agent_health()` function**

```python
def _check_agent_health(state: dict, cache: dict):
    """Check for stuck agents and surface messages to console."""
    r_agents = cache.get("r_agents", [])
    activity = cache.get("activity", {})
    now = datetime.now(timezone.utc)

    # Track already-surfaced agents to avoid spam
    surfaced = state.setdefault("_surfaced_agents", set())

    for a in r_agents:
        aid = a["agent_id"]
        if aid in surfaced:
            continue
        # Check if agent has been running with no tool events for 2+ min
        buckets = activity.get(a["session_id"], [])
        total_recent = sum(buckets) if buckets else 0
        try:
            started = datetime.fromisoformat(a["started_at"]).replace(tzinfo=timezone.utc)
            running_secs = (now - started).total_seconds()
        except Exception:
            running_secs = 0

        if running_secs > 120 and total_recent == 0:
            atype = (a.get("agent_type") or "agent")[:15]
            dur = fmt_dur(a["started_at"])
            state["console_lines"].append({
                "text": f"{atype} seems stuck (no activity, running {dur})",
                "attr": DIM,
            })
            surfaced.add(aid)

    # Clear surfaced set for agents no longer running
    running_ids = {a["agent_id"] for a in r_agents}
    surfaced -= surfaced - running_ids
```

**Step 3: Visual verification**

If any agent has been running for 2+ minutes with no tool events, a dim message should appear in the console unprompted.

**Step 4: Commit**

```bash
git add agent-top
git commit -m "feat: proactive surfacing — console alerts for stuck agents"
```

---

### Task 13: Update footer keybindings and final polish

**Files:**
- Modify: `agent-top:2081-2094` (footer)

**Step 1: Update footer hints to include console**

Update the footer help text to show `/` for console focus:

```python
    elif visible_items:
        if state.get("console_focus"):
            safe_add(stdscr, h - 1, 0, " type query  enter=submit  esc=close  ↑=history", w, DIM)
        elif state.get("focus") == "right":
            safe_add(stdscr, h - 1, 0, " j/k=scroll  h=back  /=console  tab=viz  enter=open  q=quit", w, DIM)
        elif state.get("selected", -1) >= 0:
            safe_add(stdscr, h - 1, 0, " j/k=select  l/enter=detail  /=console  h/l=stats  esc=deselect  q=quit", w, DIM)
        else:
            safe_add(stdscr, h - 1, 0, " j/k=select  /=console  h/l=stats range  tab=viz  q=quit", w, DIM)
```

**Step 2: Bump version**

Update VERSION at line 20:

```python
VERSION = "0.8.0"
```

(Check if already at 0.8.0 — if so, this is correct for the alive console feature.)

**Step 3: Visual verification — full integration test**

Run the dashboard end-to-end and verify:
1. Borders breathe (subtle brightness oscillation)
2. Heartbeat dot blinks in bottom-right corner
3. Text shimmers (rare character flicker)
4. Session sparklines color by recency (yellow → green → white → dim)
5. Console panel visible at bottom with `> ` prompt
6. `/` focuses console, typing works, Enter submits
7. Fast paths work: `help`, `agents`, `tools`, `history`, `clear`
8. Claude API works (if key set): natural language queries return results
9. Footer shows context-appropriate keybindings
10. Idle 30s+ → stats numbers drift occasionally

**Step 4: Commit**

```bash
git add agent-top
git commit -m "feat: v0.8.0 — the alive console"
```

---

## Dependency Graph

```
Task 1 (imports + state) ──→ Task 2 (breathing borders)
                          ──→ Task 3 (heartbeat cursor)
                          ──→ Task 4 (text shimmer)
                          ──→ Task 5 (warmth gradient)
                          ──→ Task 6 (idle drift)
                          ──→ Task 7 (console layout) ──→ Task 8 (console input)
                                                       ──→ Task 9 (fast paths)
                                                       ──→ Task 10 (Claude API) ──→ Task 11 (typing effect)
                                                       ──→ Task 12 (proactive surfacing)
Task 2-6 + Task 8-12     ──→ Task 13 (polish + version bump)
```

Tasks 2-6 are independent of each other (all depend on Task 1).
Tasks 8-12 are mostly independent of each other (all depend on Task 7).
Task 13 is the final integration task.
