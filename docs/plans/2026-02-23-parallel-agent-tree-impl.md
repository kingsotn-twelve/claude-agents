# Parallel Agent Tree Grouping — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Group parallel agent tool calls into collapsible tree nodes so users can see which tools belong to which agent.

**Architecture:** Add `cwd` to `tool_event` table, match tools to agents at render time using cwd + timestamp windows, render agent groups as collapsible nodes in the tree with an extra indent level for child tools.

**Tech Stack:** Python 3, curses, SQLite

---

### Task 1: Add `cwd` column to tool_event schema

**Files:**
- Modify: `ccnotify.py:175-243` (init_database — tool_event CREATE TABLE)
- Modify: `agent_top/__init__.py:167-174` (query_db — migration block)

**Step 1: Add `cwd` to tool_event CREATE TABLE in ccnotify.py**

In `ccnotify.py` line 213-224, add `cwd TEXT` to the CREATE TABLE:

```python
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_label TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    tool_input TEXT,
                    tool_response TEXT,
                    tool_use_id TEXT,
                    duration_ms INTEGER,
                    cwd TEXT
                )
            """)
```

**Step 2: Add migration in agent_top/__init__.py**

In `agent_top/__init__.py` around line 172, add `cwd` to the migration list:

```python
        for col, ctype in [("tool_input", "TEXT"), ("tool_response", "TEXT"), ("tool_use_id", "TEXT"), ("duration_ms", "INTEGER"), ("is_error", "INTEGER DEFAULT 0"), ("error_message", "TEXT"), ("cwd", "TEXT")]:
```

**Step 3: Store `cwd` in handle_pre_tool_use**

In `ccnotify.py` line 275-287, add `cwd` extraction and store it:

```python
    def handle_pre_tool_use(self, data: dict) -> None:
        session_id = data.get("session_id", "")
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        if not session_id or not tool_name:
            return
        label = self._extract_tool_label(tool_name, tool_input)
        tool_use_id = data.get("tool_use_id", "")
        cwd = data.get("cwd", "")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tool_event (session_id, tool_name, tool_label, tool_input, tool_use_id, cwd) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, tool_name, label, json.dumps(tool_input, default=str)[:4000], tool_use_id, cwd),
            )
```

**Step 4: Verify manually**

Run `agent-top` in one pane, trigger a tool call in Claude Code in another. Check the DB:
```bash
sqlite3 ~/.claude/ccnotify/ccnotify.db "SELECT id, tool_name, cwd FROM tool_event ORDER BY id DESC LIMIT 5"
```
Expected: new rows have non-empty `cwd` values.

**Step 5: Commit**

```bash
git add ccnotify.py agent_top/__init__.py
git commit -m "feat: store cwd on tool_event for agent grouping"
```

---

### Task 2: Include `cwd` in session_tools query

**Files:**
- Modify: `agent_top/__init__.py:283-298` (session_tools query)

**Step 1: Add `cwd` to the session_tools SELECT**

In `agent_top/__init__.py` line 288, add `cwd` to the SELECT columns:

```python
                for row in conn.execute(
                    """SELECT tool_name, tool_label, created_at, tool_input, tool_response, duration_ms, is_error, error_message, cwd FROM tool_event
                       WHERE session_id = ?
                       ORDER BY created_at DESC
                       LIMIT 200""",
                    (sid,),
                ):
```

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: include cwd in session_tools query"
```

---

### Task 3: Write `_match_tools_to_agents()` function

**Files:**
- Modify: `agent_top/__init__.py` (add new function before `_draw_viz_tree`)

**Step 1: Add the matching function**

Insert before `_draw_viz_tree` (around line 905):

```python
def _match_tools_to_agents(tools, agents, target_sid):
    """Match tool_events to agents by session_id + time window + cwd.

    Returns:
        agent_tools: dict[agent_id] -> [tool_event_dicts]  (tools belonging to each agent)
        agent_labels: dict[agent_id] -> str  (human-readable label from the Task tool call)
        unmatched: [tool_event_dicts]  (tools not assigned to any agent)
    """
    # Build agent time windows for this session
    session_agents = [a for a in agents if a.get("session_id") == target_sid]
    if not session_agents:
        return {}, {}, tools

    agent_tools = {a["agent_id"]: [] for a in session_agents}
    agent_labels = {}
    unmatched = []

    # Pair Task tool_events to agents by timestamp proximity (Task fires just before SubagentStart)
    task_tools = [t for t in tools if t.get("_tool_name") == "Task"]
    for agent in session_agents:
        a_start = agent.get("started_at", "")
        best_task = None
        best_delta = 6  # max 5 seconds
        for tt in task_tools:
            tt_ts = tt.get("ts", "")
            if tt_ts and a_start and tt_ts <= a_start:
                try:
                    from datetime import datetime as dt
                    t1 = dt.fromisoformat(tt_ts.replace("Z", "+00:00")) if "T" in tt_ts else dt.strptime(tt_ts, "%Y-%m-%d %H:%M:%S")
                    t2 = dt.fromisoformat(a_start.replace("Z", "+00:00")) if "T" in a_start else dt.strptime(a_start, "%Y-%m-%d %H:%M:%S")
                    delta = abs((t2 - t1).total_seconds())
                    if delta < best_delta:
                        best_delta = delta
                        best_task = tt
                except Exception:
                    pass
        if best_task:
            agent_labels[agent["agent_id"]] = best_task.get("text", agent.get("agent_type", "agent"))

    # Assign non-Task tools to agents by time window + cwd
    for t in tools:
        if t.get("_tool_name") == "Task":
            continue  # Task tool_events become agent group headers, not children
        t_ts = t.get("ts", "")
        t_cwd = t.get("_cwd", "")
        candidates = []
        for agent in session_agents:
            a_start = agent.get("started_at", "")
            a_stop = agent.get("stopped_at")
            if not a_start:
                continue
            if t_ts >= a_start and (a_stop is None or t_ts <= a_stop):
                candidates.append(agent)
        if len(candidates) == 1:
            agent_tools[candidates[0]["agent_id"]].append(t)
        elif len(candidates) > 1:
            # Prefer cwd match
            cwd_match = [a for a in candidates if a.get("cwd") and a["cwd"] == t_cwd]
            if len(cwd_match) == 1:
                agent_tools[cwd_match[0]["agent_id"]].append(t)
            else:
                # Fall back to most recently started
                best = max(candidates, key=lambda a: a.get("started_at", ""))
                agent_tools[best["agent_id"]].append(t)
        else:
            unmatched.append(t)

    return agent_tools, agent_labels, unmatched
```

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: add _match_tools_to_agents function"
```

---

### Task 4: Pass `cwd` through timeline events

**Files:**
- Modify: `agent_top/__init__.py:935-949` (tool timeline entry creation)

**Step 1: Add `_cwd` to tool timeline entries**

In `_draw_viz_tree`, when building tool timeline entries (around line 939-949), add the `_cwd` field:

```python
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
            "_cwd": t.get("cwd", ""),
        })
```

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: pass cwd through timeline tool events"
```

---

### Task 5: Restructure timeline grouping with agent groups

**Files:**
- Modify: `agent_top/__init__.py:959-990` (group-by-prompt logic in `_draw_viz_tree`)

This is the core change. After building the flat timeline, instead of just grouping tools under prompts, we also group tools under agents.

**Step 1: Replace the group-by-prompt section**

Replace lines 959-990 in `_draw_viz_tree` with the new grouping logic:

```python
    # Match tools to agents
    all_agents = r_agents + c_agents
    agent_tools, agent_labels, unmatched_tools = _match_tools_to_agents(timeline, all_agents, target_sid)

    # Rebuild timeline: replace flat tool/agent entries with grouped structure
    # Keep prompts and unmatched tools in chronological order,
    # insert agent groups where the agent's started_at falls in the timeline
    grouped_timeline = []
    # Collect agent group events
    agent_group_events = []
    for a in children + completed:
        aid = a["agent_id"]
        a_tools = agent_tools.get(aid, [])
        adur = fmt_dur(a["started_at"], a.get("stopped_at"))
        running = a in children
        label = agent_labels.get(aid, a["agent_type"])
        agent_group_events.append({
            "ts": a.get("started_at", ""),
            "kind": "agent_group",
            "text": f"{label}  {adur}",
            "running": running,
            "_agent_id": aid,
            "_children": a_tools,
            "_child_count": len(a_tools),
        })

    # Merge: prompts, unmatched tools, agent groups — sorted chronologically
    merged = []
    for ev in timeline:
        if ev["kind"] == "prompt":
            merged.append(ev)
    for ev in unmatched_tools:
        merged.append(ev)
    for ev in agent_group_events:
        merged.append(ev)
    merged.sort(key=lambda e: e.get("ts", ""))

    # Group by prompt: events AFTER a prompt are its children
    groups = []
    current_prompt = None
    current_children = []
    for ev in merged:
        if ev["kind"] == "prompt":
            if current_prompt is not None or current_children:
                groups.append((current_prompt, current_children))
            current_prompt = ev
            current_children = []
        else:
            current_children.append(ev)
    if current_prompt is not None or current_children:
        groups.append((current_prompt, current_children))
    # Reverse so newest prompt is first; children stay in execution order
    groups.reverse()

    # Per-prompt collapse + agent collapse: expand into final timeline
    collapsed = state.setdefault("_collapsed_prompts", set())
    collapsed_agents = state.setdefault("_collapsed_agents", set())
    timeline = []
    for prompt_ev, prompt_children in groups:
        if prompt_ev:
            prompt_key = prompt_ev.get("ts", "")
            prompt_ev["_prompt_key"] = prompt_key
            # Count all children including nested agent tool children
            total = 0
            for c in prompt_children:
                if c.get("kind") == "agent_group":
                    total += 1 + c.get("_child_count", 0)
                else:
                    total += 1
            prompt_ev["_child_count"] = total
            prompt_ev["_collapsed"] = prompt_key in collapsed
            timeline.append(prompt_ev)
            if prompt_key not in collapsed:
                for child in prompt_children:
                    if child.get("kind") == "agent_group":
                        aid = child.get("_agent_id", "")
                        is_collapsed = aid in collapsed_agents
                        child["_collapsed"] = is_collapsed
                        if is_collapsed:
                            child["text"] = child["text"]  # label stays same, suffix added at render
                        timeline.append(child)
                        if not is_collapsed:
                            for agent_tool in child.get("_children", []):
                                agent_tool["_under_agent"] = True
                                timeline.extend([agent_tool])
                    else:
                        timeline.append(child)
        else:
            timeline.extend(prompt_children)
```

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: restructure timeline with agent group nesting"
```

---

### Task 6: Update tree rendering for agent groups + extra indent

**Files:**
- Modify: `agent_top/__init__.py:1028-1117` (rendering loop in `_draw_viz_tree`)

**Step 1: Add agent_group to kind maps and update indentation**

Update the kind_colors and kind_icons dicts and the indent logic:

```python
    kind_colors = {"prompt": WHITE, "tool": YELLOW, "agent": MAGENTA, "agent_group": MAGENTA}
    kind_icons = {"prompt": "\u25b8", "tool": "\u2502", "agent": "\u25c6", "agent_group": "\u25c6"}
```

Then in the rendering loop (line 1037+), update the icon/suffix logic for `agent_group`:

For the icon selection block (lines 1043-1052), add agent_group handling:

```python
        if kind == "prompt" and ev.get("_collapsed"):
            icon = "\u25b6"  # ▶ collapsed
            n = ev.get("_child_count", 0)
            suffix = f"  ({n})" if n else ""
        elif kind == "prompt":
            icon = "\u25bc"  # ▼ expanded
            suffix = ""
        elif kind == "agent_group" and ev.get("_collapsed"):
            icon = "\u25b6"  # ▶ collapsed
            n = ev.get("_child_count", 0)
            suffix = f"  ({n})" if n else ""
        elif kind == "agent_group":
            icon = "\u25bc"  # ▼ expanded
            suffix = ""
        else:
            icon = kind_icons.get(kind, " ")
            suffix = ""
```

For the indent logic (line 1069), add the extra level for tools under agents:

```python
        # Indent: prompt=0, agent_group/tool=2, tool-under-agent=4
        if kind == "prompt":
            indent = 0
        elif ev.get("_under_agent"):
            indent = 4
        else:
            indent = 2
```

For the suffix display, apply it to both prompts and agent_groups (update the text truncation around line 1074):

```python
        if suffix and kind in ("prompt", "agent_group") and ev.get("_collapsed"):
            text = text[:text_w - len(suffix)] + suffix
```

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: render agent groups with collapse icons and extra indent"
```

---

### Task 7: Add agent group collapse/expand interaction

**Files:**
- Modify: `agent_top/__init__.py:2553-2570` (space/enter key handler)

**Step 1: Add agent_group toggle handling**

In the space/enter handler (line 2553+), add a branch for `agent_group` after the `prompt` branch:

```python
            elif state.get("focus") == "right":
                tl = state.get("_tree_timeline", [])
                tc = state.get("tree_cursor", 0)
                if 0 <= tc < len(tl):
                    ev = tl[tc]
                    if ev.get("kind") == "prompt":
                        pk = ev.get("_prompt_key", "")
                        collapsed = state.setdefault("_collapsed_prompts", set())
                        if pk in collapsed:
                            collapsed.discard(pk)
                        else:
                            collapsed.add(pk)
                        state["_expanded_tool"] = -1
                    elif ev.get("kind") == "agent_group":
                        aid = ev.get("_agent_id", "")
                        collapsed_agents = state.setdefault("_collapsed_agents", set())
                        if aid in collapsed_agents:
                            collapsed_agents.discard(aid)
                        else:
                            collapsed_agents.add(aid)
                        state["_expanded_tool"] = -1
                    elif ev.get("kind") == "tool":
                        if state.get("_expanded_tool") == tc:
                            state["_expanded_tool"] = -1
                        else:
                            state["_expanded_tool"] = tc
```

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "feat: space/enter toggles agent group collapse"
```

---

### Task 8: Remove old flat agent entries from timeline

**Files:**
- Modify: `agent_top/__init__.py:951-957` (agent timeline entry creation)

The old code adds agents as flat `kind: "agent"` entries alongside tools. Now that agents are rendered as `agent_group` with children, remove the old flat agent entries from the timeline builder.

**Step 1: Remove the old agent timeline entries**

Delete or comment out lines 951-957:

```python
    # Agents are now rendered as agent_groups with nested children (Task 5).
    # Don't add flat agent entries to the timeline.
    children = [a for a in r_agents if a["session_id"] == target_sid and a.get("agent_type")]
    completed = [a for a in c_agents if a["session_id"] == target_sid and a.get("agent_type")][:5]
```

Keep the `children` and `completed` variables since they're used by `_match_tools_to_agents`, but remove the `timeline.append` loop.

**Step 2: Commit**

```bash
git add agent_top/__init__.py
git commit -m "refactor: remove flat agent entries from timeline (now grouped)"
```

---

### Task 9: Manual end-to-end test

**Step 1: Run agent-top**

```bash
agent-top
```

**Step 2: In another terminal, start Claude Code and trigger parallel agents**

```
Tell Claude: "spawn 3 agents that each read a different file"
```

**Step 3: Verify in agent-top:**

- [ ] Each agent appears as a collapsible `◆` node with its description
- [ ] Tools under each agent are indented one extra level
- [ ] Space/enter on agent group toggles collapse
- [ ] Collapsed agent shows `▶ label (N)` with child count
- [ ] Unmatched tools (before/after agents) show at normal indent
- [ ] Prompt collapse still works (collapses everything including agent groups)
- [ ] Non-agent sessions (no parallel agents) still render correctly

**Step 4: Fix any issues found**

**Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: parallel agent tree rendering issues"
```
