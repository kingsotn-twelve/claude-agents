# Tool Deep-Dive + Error Tracking — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make tool calls expandable inline in the TREE panel (showing full input + smart response summary) and add PostToolUseFailure error tracking with red markers.

**Architecture:** Two backend changes (new hook handler + DB columns) feed into three UI changes (error markers, inline expansion, smart summaries). All rendering happens in the existing `_draw_interleaved_tree()` function. Timeline items already carry `_raw_input` and `_tool_name`; we extend them with response, duration, and error data.

**Tech Stack:** Python stdlib (curses, sqlite3, json). No new dependencies.

---

### Task 1: Add PostToolUseFailure handler to ccnotify

**Files:**
- Modify: `agent_top/_ccnotify.py:295-320` (near existing `handle_post_tool_use`)
- Modify: `agent_top/_ccnotify.py:570-571` (valid events list)
- Modify: `agent_top/_ccnotify.py:612-617` (event dispatch)

**Step 1: Add `is_error` and `error_message` columns to DB init**

In `_ccnotify.py`, find the `_ensure_tables` method. After the existing `tool_event` table creation, add auto-migration for the two new columns. Find where `tool_input`, `tool_response`, etc. are added (similar pattern already exists for those columns).

Add to the column migration loop in `_ensure_tables()`:
```python
# After existing tool_event column migrations, add:
for col, ctype in [("is_error", "INTEGER DEFAULT 0"), ("error_message", "TEXT")]:
    try:
        conn.execute(f"ALTER TABLE tool_event ADD COLUMN {col} {ctype}")
    except sqlite3.OperationalError:
        pass
```

**Step 2: Add the handler method**

Add `handle_post_tool_use_failure()` right after `handle_post_tool_use()` (after line 320):

```python
def handle_post_tool_use_failure(self, data: dict) -> None:
    """Mark a tool event as failed and store the error message."""
    session_id = data.get("session_id", "")
    tool_use_id = data.get("tool_use_id", "")
    error = data.get("error", "")
    if not session_id or not tool_use_id:
        return
    with sqlite3.connect(self.db_path) as conn:
        row = conn.execute(
            "SELECT id, created_at FROM tool_event WHERE tool_use_id = ? LIMIT 1",
            (tool_use_id,),
        ).fetchone()
        if row:
            try:
                start = datetime.fromisoformat(row[1])
                dur_ms = int((datetime.now() - start).total_seconds() * 1000)
            except Exception:
                dur_ms = None
            conn.execute(
                "UPDATE tool_event SET is_error = 1, error_message = ?, duration_ms = ? WHERE id = ?",
                (error[:4000], dur_ms, row[0]),
            )
            conn.commit()
    logging.info(f"PostToolUseFailure: {tool_use_id} session={session_id} error={error[:80]}")
```

**Step 3: Register the event**

In the `valid` list at line 570, add `"PostToolUseFailure"`:
```python
valid = ["SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop",
         "Notification", "PreToolUse", "PostToolUse", "PostToolUseFailure", "TeammateIdle", "TaskCompleted"]
```

In the dispatch block (after `elif event == "PostToolUse":` at line 612), add:
```python
elif event == "PostToolUseFailure":
    tracker.handle_post_tool_use_failure(data)
```

**Step 4: Commit**

```bash
git add agent_top/_ccnotify.py
git commit -m "feat: add PostToolUseFailure handler with error tracking columns"
```

---

### Task 2: Add PostToolUseFailure to hook setup output

**Files:**
- Modify: `agent_top/__init__.py:2364-2365` (setup hook config output)

**Step 1: Add the hook line**

Change line 2365 from:
```python
    "PostToolUse":      [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} PostToolUse"}}]}}]
```
to:
```python
    "PostToolUse":      [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} PostToolUse"}}]}}],
    "PostToolUseFailure": [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} PostToolUseFailure"}}]}}]
```

Note the comma added to the PostToolUse line.

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: include PostToolUseFailure in setup hook config"
```

---

### Task 3: Add DB migration + query changes in dashboard

**Files:**
- Modify: `agent_top/__init__.py:165` (column migration)
- Modify: `agent_top/__init__.py:281` (session_tools query)

**Step 1: Add column migration**

At line 165, extend the existing migration list:
```python
for col, ctype in [("tool_input", "TEXT"), ("tool_response", "TEXT"), ("tool_use_id", "TEXT"), ("duration_ms", "INTEGER"), ("is_error", "INTEGER DEFAULT 0"), ("error_message", "TEXT")]:
```

**Step 2: Add columns to session_tools query**

At line 281, change the SELECT to include the new columns:
```sql
SELECT tool_name, tool_label, created_at, tool_input, tool_response, duration_ms, is_error, error_message FROM tool_event
```

**Step 3: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: add is_error/error_message to DB migration and queries"
```

---

### Task 4: Carry error + response data on timeline items

**Files:**
- Modify: `agent_top/__init__.py:786-792` (timeline item construction in `_draw_interleaved_tree`)

**Step 1: Extend the timeline item dict**

Change lines 786-792 from:
```python
    # Tools
    for t in (session_tools.get(target_sid, []) or tool_events.get(target_sid, [])):
        dur_ms = t.get("duration_ms")
        dur_str = f" {dur_ms}ms" if dur_ms else ""
        desc = friendly_tool(t["tool_name"], t.get("tool_label", ""))
        timeline.append({"ts": t.get("created_at", ""), "kind": "tool", "text": f"{desc}{dur_str}",
                         "_raw_input": t.get("tool_input"), "_tool_name": t.get("tool_name")})
```

To:
```python
    # Tools
    for t in (session_tools.get(target_sid, []) or tool_events.get(target_sid, [])):
        dur_ms = t.get("duration_ms")
        desc = friendly_tool(t["tool_name"], t.get("tool_label", ""))
        is_err = bool(t.get("is_error"))
        timeline.append({
            "ts": t.get("created_at", ""),
            "kind": "tool",
            "text": desc,
            "_raw_input": t.get("tool_input"),
            "_raw_response": t.get("tool_response"),
            "_tool_name": t.get("tool_name"),
            "_duration_ms": dur_ms,
            "_is_error": is_err,
            "_error_message": t.get("error_message", ""),
        })
```

Note: duration is no longer baked into `text` — it will be rendered separately with color coding.

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: carry full tool data (response, duration, error) on timeline items"
```

---

### Task 5: Render error markers + duration colors in TREE

**Files:**
- Modify: `agent_top/__init__.py:842-896` (render loop in `_draw_interleaved_tree`)

**Step 1: Update kind_icons and kind_colors to handle errors**

Replace the static icon/color lookup at line 842-843:
```python
    kind_colors = {"prompt": WHITE, "tool": YELLOW, "agent": MAGENTA}
    kind_icons = {"prompt": "\u25b8", "tool": "\u2502", "agent": "\u25c6"}
```

These stay as defaults but we override per-item in the loop.

**Step 2: In the render loop (line 846+), override icon/color for errors and add duration**

In the loop body, after getting `kind`, `icon`, `color` (around line 852-853), add:

```python
        # Error override
        is_err = ev.get("_is_error", False)
        if is_err and kind == "tool":
            icon = "\u2717"  # ✗
            color = RED

        # Duration string with color
        dur_ms = ev.get("_duration_ms")
        dur_color = DIM
        dur_str = ""
        if dur_ms is not None and kind == "tool":
            if dur_ms < 1000:
                dur_str = f"{dur_ms}ms"
                dur_color = GREEN
            elif dur_ms < 5000:
                dur_str = f"{dur_ms / 1000:.1f}s"
                dur_color = YELLOW
            else:
                dur_str = f"{dur_ms / 1000:.1f}s"
                dur_color = RED
```

Then in the actual safe_add calls for non-prompt items (around line 888-896), after drawing the icon+text, add the duration right-aligned:

```python
            # Draw duration right-aligned
            if dur_str:
                dur_x = x + w - len(dur_str) - 3
                if dur_x > icon_col + len(text) + 2:
                    dur_attr = dur_color | (curses.A_REVERSE if is_cursor else 0)
                    safe_add(stdscr, pr, dur_x, dur_str, rw, dur_attr)
```

**Step 3: Verify visually**

Run: `agent-top` — tool events should show with duration right-aligned. Any errors (once PostToolUseFailure fires) should show red `✗`.

**Step 4: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: red error markers + color-coded duration in TREE timeline"
```

---

### Task 6: Add expand/collapse state + Enter toggle

**Files:**
- Modify: `agent_top/__init__.py:2294-2320` (Enter key handler)
- Modify: `agent_top/__init__.py:758` (tree function, for expand state)

**Step 1: Add expand state tracking**

The state dict already tracks `tree_cursor`. Add `_expanded_tool` to track which timeline index is expanded (or -1 for none).

In the Enter key handler at line 2294, change the right-panel branch:

```python
            elif state["focus"] == "right":
                tl = state.get("_tree_timeline", [])
                tc = state.get("tree_cursor", 0)
                if 0 <= tc < len(tl):
                    ev = tl[tc]
                    if ev.get("kind") == "tool":
                        # Toggle expand/collapse
                        if state.get("_expanded_tool") == tc:
                            state["_expanded_tool"] = -1  # collapse
                        else:
                            state["_expanded_tool"] = tc  # expand
```

This replaces the existing iTerm2 file-opening behavior. If we want to keep that, we can move it to a different key later, but expand/collapse is the primary action now.

**Step 2: Reset expand on navigation**

When `tree_cursor` changes (j/k), do NOT auto-collapse — let the user navigate while something is expanded. But when switching sessions or pressing Esc, reset:

In the Esc handler (where `focus` goes back to "left"), add:
```python
state["_expanded_tool"] = -1
```

**Step 3: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: Enter toggles tool event expand/collapse in TREE"
```

---

### Task 7: Render expanded tool content inline

**Files:**
- Modify: `agent_top/__init__.py:846-896` (render loop in `_draw_interleaved_tree`)

This is the core rendering task. When `state["_expanded_tool"] == idx`, render extra rows after the tool event line.

**Step 1: Add `_render_tool_expansion()` helper function**

Add this before `_draw_interleaved_tree()`:

```python
def _format_smart_summary(tool_name, raw_response, max_lines=8, max_width=70):
    """Parse tool response into a smart summary based on tool type."""
    if not raw_response:
        return ["(no response)"]
    try:
        resp = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
    except Exception:
        # Raw string response
        lines = str(raw_response).replace("\n", " ")[:max_width * max_lines]
        return [lines[i:i+max_width] for i in range(0, len(lines), max_width)][:max_lines]

    result = []
    resp_str = str(resp)

    if tool_name == "Read":
        content = resp.get("content", resp_str) if isinstance(resp, dict) else resp_str
        lines = content.split("\n") if isinstance(content, str) else [resp_str]
        total = len(lines)
        if total <= max_lines:
            result = [l[:max_width] for l in lines]
        else:
            result = [l[:max_width] for l in lines[:3]]
            result.append(f"  ... ({total} lines total)")
            result.extend(l[:max_width] for l in lines[-2:])
    elif tool_name == "Bash":
        output = resp.get("output", resp.get("stdout", resp_str)) if isinstance(resp, dict) else resp_str
        lines = output.split("\n") if isinstance(output, str) else [str(output)]
        exit_code = resp.get("exitCode", resp.get("exit_code", "")) if isinstance(resp, dict) else ""
        if exit_code != "":
            result.append(f"exit {exit_code}")
        tail = lines[-(max_lines - len(result)):] if len(lines) > max_lines else lines
        result.extend(l[:max_width] for l in tail)
    elif tool_name == "Grep":
        if isinstance(resp, dict):
            matches = resp.get("matches", resp.get("files", []))
            if isinstance(matches, list):
                result.append(f"{len(matches)} matches")
                for m in matches[:5]:
                    result.append(f"  {str(m)[:max_width - 2]}")
            else:
                result.append(str(matches)[:max_width])
        else:
            lines = resp_str.split("\n")
            result.append(f"{len(lines)} matches")
            result.extend(l[:max_width] for l in lines[:5])
    elif tool_name in ("Edit", "Write"):
        if isinstance(resp, dict):
            success = resp.get("success", True)
            fp = resp.get("filePath", resp.get("file_path", ""))
            result.append(f"{'ok' if success else 'FAIL'}: {os.path.basename(fp)}" if fp else ("ok" if success else "FAIL"))
        else:
            result.append(resp_str[:max_width])
    elif tool_name == "Glob":
        if isinstance(resp, (list, dict)):
            files = resp if isinstance(resp, list) else resp.get("files", resp.get("matches", []))
            if isinstance(files, list):
                result.append(f"{len(files)} files")
                for f in files[:5]:
                    result.append(f"  {str(f)[:max_width - 2]}")
            else:
                result.append(str(files)[:max_width])
        else:
            result.append(resp_str[:max_width])
    else:
        # Default: truncated raw
        flat = resp_str.replace("\n", " ")
        result = [flat[i:i+max_width] for i in range(0, min(len(flat), max_width * max_lines), max_width)][:max_lines]

    return result[:max_lines] if result else ["(empty)"]


def _render_tool_expansion(stdscr, ev, pr, col, rw, max_row, is_error=False):
    """Render expanded tool detail lines. Returns number of rows consumed."""
    color = RED if is_error else DIM
    resp_color = RED if is_error else GREEN
    separator = "\u254c" * min(55, rw - col - 2)  # ╌ repeating
    rows_drawn = 0
    max_width = rw - col - 4

    def draw(row, text, c):
        nonlocal rows_drawn
        if row < max_row:
            safe_add(stdscr, row, col, text[:max_width + 4], rw, c)
            rows_drawn += 1

    # Top separator
    draw(pr, f"  {separator}", color)
    pr += 1

    # Input section
    raw_input = ev.get("_raw_input")
    if raw_input:
        try:
            ti = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
            for k, v in list(ti.items())[:6]:
                vs = str(v).replace("\n", " ")[:max_width - len(k) - 4]
                draw(pr, f"  {k}: {vs}", color)
                pr += 1
        except Exception:
            draw(pr, f"  {str(raw_input)[:max_width]}", color)
            pr += 1

    # Response/Error section
    if is_error:
        err_msg = ev.get("_error_message", "")
        if err_msg:
            draw(pr, "  ERROR", RED | curses.A_BOLD)
            pr += 1
            for line in err_msg.split("\n")[:8]:
                draw(pr, f"  {line[:max_width]}", RED)
                pr += 1
    else:
        raw_resp = ev.get("_raw_response")
        tool_name = ev.get("_tool_name", "")
        summary_lines = _format_smart_summary(tool_name, raw_resp, max_lines=8, max_width=max_width - 4)
        for line in summary_lines:
            draw(pr, f"  \u2192 {line}", resp_color)  # → prefix
            pr += 1

    # Bottom separator
    draw(pr, f"  {separator}", color)
    rows_drawn += 1

    return rows_drawn
```

**Step 2: Integrate into the render loop**

In the render loop at line 846, after drawing each tool event line, check if it's expanded and render the expansion:

After `pr += 1` at line 896, add:

```python
        # Render expansion if this tool is expanded
        if kind == "tool" and state.get("_expanded_tool") == idx:
            expansion_rows = _render_tool_expansion(
                stdscr, ev, pr, col_start, rw, y + h,
                is_error=ev.get("_is_error", False)
            )
            pr += expansion_rows
```

**Step 3: Fix scroll accounting**

The auto-scroll logic at lines 832-838 uses `visible_rows = h` to calculate how many items fit. With expansion, one item can take multiple rows. This is tricky to get perfect, but a simple approach: when expanded, count the expanded item as ~12 rows instead of 1 in the scroll calculation. Add after line 825:

```python
    # Estimate expansion rows for scroll calculation
    expanded_idx = state.get("_expanded_tool", -1)
    expansion_height = 12 if 0 <= expanded_idx < len(timeline) else 0
```

And adjust `visible_rows`:
```python
    visible_rows = max(1, h - expansion_height)
```

**Step 4: Verify visually**

Run: `agent-top`, select a session, `j/k` to a tool event, press Enter. Should see expanded input + response below the tool line.

**Step 5: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: inline tool expansion with smart response summaries"
```

---

### Task 8: Add ERRORS section to STATS panel

**Files:**
- Modify: `agent_top/__init__.py` (stats query section + stats rendering)

**Step 1: Find the stats query section**

Search for where `top_tools` or `TOOLS` stats are queried. It will be in `_refresh_data()`. Add a parallel query for errors:

```python
        # Error stats
        try:
            data["error_stats"] = []
            for row in conn.execute(
                f"""SELECT te.tool_name, p.cwd, COUNT(*) as cnt
                    FROM tool_event te
                    LEFT JOIN prompt p ON te.session_id = p.session_id
                    WHERE te.is_error = 1 {time_filter}
                    GROUP BY te.tool_name, p.cwd
                    ORDER BY cnt DESC
                    LIMIT 8""",
            ):
                data["error_stats"].append(dict(row))
        except sqlite3.OperationalError:
            data["error_stats"] = []
```

**Step 2: Find the STATS rendering section**

Search for where "TOOLS" header is drawn. After the TOOLS section, add:

```python
        # ERRORS section
        error_stats = cache.get("error_stats", [])
        if error_stats and pr < max_stat_row:
            P(pr, 2, "ERRORS", RED | curses.A_BOLD); pr += 1
            max_cnt = max(s["cnt"] for s in error_stats) if error_stats else 1
            for s in error_stats:
                if pr >= max_stat_row:
                    break
                tag = f"[{os.path.basename(s.get('cwd', '') or '')}]"
                bar_w = 8
                filled = int(s["cnt"] / max_cnt * bar_w) if max_cnt else 0
                bar = "\u2588" * filled + "\u2591" * (bar_w - filled)
                P(pr, 2, f"{tag:16s} {s['tool_name']:16s} {bar} {s['cnt']}", RED)
                pr += 1
            pr += 1  # blank line after section
```

**Step 3: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: add ERRORS section to STATS panel"
```

---

### Task 9: Manual test + final commit

**Step 1: Reinstall the hook**

```bash
rm ~/.claude/ccnotify/ccnotify.py
agent-top --setup
```

Copy the new hooks JSON and update `~/.claude/settings.json` to include `PostToolUseFailure`.

**Step 2: Verify end-to-end**

1. Run `agent-top` in one terminal
2. Start a Claude Code session in another
3. Have Claude make tool calls — verify they appear in TREE with duration
4. Navigate with `j/k`, press Enter to expand a tool — verify input + smart summary
5. Press Enter again to collapse
6. Trigger a tool failure (e.g., have Claude read a nonexistent file) — verify red `✗` marker
7. Expand the error — verify error message shows in red
8. Check STATS — verify ERRORS section appears if errors exist

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: tool deep-dive + error tracking in TREE panel"
```
