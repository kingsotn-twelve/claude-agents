# claude-agents btop-rewrite — Implementation Spec

**Branch:** `btop-rewrite`
**Goal:** Rewrite `claude-agents` dashboard as a btop-style TUI — rounded box panels, component architecture, braille activity graphs, dirty-flag redraws. Keep all data sources and DB queries identical to `main`.

---

## Why rewrite

The current `claude-agents` is a 900-line monolithic `draw()` function. It works but:
- Layout is hard-coded with manual column math
- No box borders — hard to read at a glance
- Right panel only appears when terminal ≥80 cols and stats exist
- No activity graphs — durations are the only visual signal
- Resize causes jank (no partial redraw)
- Adding new panels requires touching the entire draw() function

The rewrite introduces:
- **Box panels** with rounded `╭╮╰╯` borders and inline titles
- **Component classes** — each panel owns its own draw logic
- **Braille graphs** — activity sparklines per session/agent
- **Layout manager** — panels adapt to terminal size
- **Dirty flags** — borders only redrawn on resize or data change

---

## Visual design

### Character set

```python
SYMBOLS = {
    "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
    "h":  "─", "v":  "│",
    "lt": "├", "rt": "┤",  # side junctions (for title cutouts)
}
```

Title embedded in top border:
```
╭── TEAMS  my-project · 1✓ 2● 2○ ──────────────────────────────╮
│                                                               │
╰───────────────────────────────────────────────────────────────╯
```

### Color pairs (curses)

| ID | Name        | Use                            |
|----|-------------|--------------------------------|
| 1  | GREEN       | Idle/ok state                  |
| 2  | WHITE       | Primary content                |
| 3  | CYAN        | Panel titles, team names       |
| 4  | YELLOW      | Durations, running state       |
| 5  | DIM (grey)  | Secondary info, borders        |
| 6  | MAGENTA     | Subagent type names            |
| 7  | RED         | Errors                         |
| 8  | CYAN_DIM    | Session IDs, short hashes      |

### Braille activity graph

Each session/agent gets a 10-char braille sparkline showing tool activity over the last 60s. Braille dots represent tool events per 6s bucket:

```
⣿⣷⣦⣄⣀⠀⠀⠀⠀⠀  (activity dying off)
⠀⠀⠀⣀⣤⣶⣿⣿⣷⣦  (ramping up)
```

Use the 25-char braille set: `⠀⠂⠄⠆⠈⠐⠒⠔⠖⠘⠠⠢⠤⠦⠨⠰⠲⠴⠶⠸⡀⡂⡄⡆⡈` mapped by combining two height values (0–4 each → index = h1*5 + h2).

---

## Layout

### Default layout (terminal ≥ 100 cols)

```
╭── TEAMS ──────────────────────────────╮╭── DETAIL ────────────────────────────╮
│ ├─ ◉ researcher  3m  abc123  ⣿⣷⣦⣄⣀⠀⠀ ││ abc12 · my-project/researcher · 3m  │
│ └─ ◉ implementer 1m  def456  ⠀⠀⠀⣀⣤⣶ ││ ─────────────────────────────────── │
╰───────────────────────────────────────╯│ ● Implement auth endpoints           │
╭── SESSIONS  2 running ────────────────╮│ ○ Write unit tests                   │
│ ◉  5m  ghi789  fix login  ⣿⣿⣷⣦⣄⣀⠀⠀⠀ ││ ✓ Research API patterns              │
│    └ Read→auth.ts  Bash→npm test      │╰──────────────────────────────────────╯
╰───────────────────────────────────────╯
╭── HISTORY ────────────────────────────╮
│ 14:23  3m  ▸ debug                    │
│ 14:19  1m  add auth middleware        │
╰───────────────────────────────────────╯
```

### Narrow layout (terminal < 100 cols)

Stacks vertically. Detail panel hidden; selecting item shows inline expansion below it.

### Panel sizing rules

```
LEFT_W  = (total_w * 3) // 5   # same ratio as current
RIGHT_W = total_w - LEFT_W - 1 # -1 for divider (now the box border)

TEAMS_H   = 2 + len(visible_team_members)          # min 3
SESSIONS_H = 2 + len(visible_sessions) * 2         # 2 rows per session
HISTORY_H = remaining rows after TEAMS + SESSIONS
DETAIL_H  = total_h - 2                            # full height right
```

---

## Architecture

### File structure

Keep as a **single executable file** (`claude-agents`) — same as today. Organize into sections with clear headers:

```python
# ── CONSTANTS & SYMBOLS ──────────────────────────────────────
# ── DATA QUERIES ─────────────────────────────────────────────  ← keep from main, unchanged
# ── FORMATTERS ───────────────────────────────────────────────  ← keep from main, unchanged
# ── BRAILLE GRAPH ────────────────────────────────────────────  ← new
# ── BOX DRAWING ──────────────────────────────────────────────  ← new
# ── COMPONENTS ───────────────────────────────────────────────  ← new
# ── LAYOUT MANAGER ───────────────────────────────────────────  ← new
# ── MAIN LOOP ────────────────────────────────────────────────  ← simplified
```

### Component base class

```python
class Panel:
    """A bordered box panel that owns a region of the screen."""

    def __init__(self, y: int, x: int, h: int, w: int, title: str = ""):
        self.y, self.x, self.h, self.w = y, x, h, w
        self.title = title
        self.dirty = True       # full redraw needed (resize, first draw)
        self._win = None        # curses subwindow (created lazily)

    def resize(self, y, x, h, w):
        self.y, self.x, self.h, self.w = y, x, h, w
        self.dirty = True

    def draw(self, stdscr, data: dict, state: dict, frame: int):
        if self.dirty:
            self._draw_border(stdscr)
            self.dirty = False
        self._draw_content(stdscr, data, state, frame)

    def _draw_border(self, stdscr):
        """Draw rounded box border with embedded title."""
        # top border
        # side borders
        # bottom border
        # embed title into top border if present
        pass

    def _draw_content(self, stdscr, data, state, frame):
        """Override in subclass."""
        pass

    def inner_h(self) -> int: return self.h - 2
    def inner_w(self) -> int: return self.w - 2
    def inner_y(self) -> int: return self.y + 1
    def inner_x(self) -> int: return self.x + 1
```

### Panels to implement

```python
class TeamsPanel(Panel):     # TEAMS box — team members, task counts
class SessionsPanel(Panel):  # SESSIONS box — solo active sessions + subagents
class HistoryPanel(Panel):   # HISTORY box — completed agents + prompts
class DetailPanel(Panel):    # DETAIL box — task list or transcript or stats
class TitleBar:              # not a Panel — full-width header row (no border)
```

### Braille graph

```python
BRAILLE = "⠀⠂⠄⠆⠈⠐⠒⠔⠖⠘⠠⠢⠤⠦⠨⠰⠲⠴⠶⠸⡀⡂⡄⡆⡈"  # 25 chars

def sparkline(buckets: list[int], width: int = 10) -> str:
    """
    buckets: list of int counts, one per time slot.
    Normalize to 0-4, pair up, return braille string of `width` chars.
    """
    # take last width*2 buckets, pad left with 0 if short
    # normalize each to 0-4
    # pair: index = high*5 + low
    # return "".join(BRAILLE[i] for i in indices)
```

Activity data: extend `query_db()` to return `activity_buckets` per session — 10 buckets of 6s each, counting tool_events. Already in DB as `tool_event` table.

```python
# In query_db(), add:
for sid in active_sids:
    buckets = []
    for slot in range(10):
        start = slot * 6
        end   = start + 6
        count = conn.execute(
            """SELECT COUNT(*) FROM tool_event
               WHERE session_id = ?
                 AND created_at > datetime('now', ?)
                 AND created_at <= datetime('now', ?)""",
            (sid, f"-{60 - start} seconds", f"-{60 - end} seconds")
        ).fetchone()[0]
        buckets.append(count)
    data["activity"][sid] = buckets
```

---

## Box drawing helper

```python
def draw_box(stdscr, y: int, x: int, h: int, w: int,
             title: str = "", title_attr=0, border_attr=0):
    """
    Draw a rounded-corner box. Title is embedded left-aligned in top border.

    ╭── TITLE ──────╮
    │               │
    ╰───────────────╯
    """
    DIM = curses.color_pair(5)

    # Top
    top = SYMBOLS["tl"] + SYMBOLS["h"] * (w - 2) + SYMBOLS["tr"]
    if title:
        label = f" {title} "
        insert_at = 2
        top = top[:insert_at] + label + top[insert_at + len(label):]
    safe_add(stdscr, y, x, top, x + w, border_attr or DIM)
    if title:
        safe_add(stdscr, y, x + 2, f" {title} ", x + w, title_attr or CYAN)

    # Sides
    for row in range(y + 1, y + h - 1):
        safe_add(stdscr, row, x,         SYMBOLS["v"], x + w, DIM)
        safe_add(stdscr, row, x + w - 1, SYMBOLS["v"], x + w, DIM)

    # Bottom
    bot = SYMBOLS["bl"] + SYMBOLS["h"] * (w - 2) + SYMBOLS["br"]
    safe_add(stdscr, y + h - 1, x, bot, x + w, DIM)
```

---

## What to keep unchanged from `main`

Copy these functions verbatim — they have no UI concerns:

- `query_db()` — extend with `activity` buckets (see above)
- `query_teams()` — unchanged
- `read_team_tasks()` — unchanged
- `dir_tag()` — unchanged
- `find_transcript()` — unchanged
- `read_preview_lines()` — unchanged
- `open_agent_in_iterm2()` — unchanged
- `fmt_dur()` — unchanged
- `fmt_time()` — unchanged
- `short_id()`, `short_session()`, `short_prompt()` — unchanged
- `safe_add()` — unchanged

---

## State model

```python
state = {
    "selected":       -1,          # index into visible_items list
    "visible_items":  [],          # list of selectable dicts (teammates + subagents)
    "last_h":         0,           # last known terminal height (resize detection)
    "last_w":         0,           # last known terminal width
}
```

`visible_items` replaces `visible_agents` — same structure, includes both teammates (`is_teammate=True`) and subagents.

---

## Main loop

```python
def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(1000)
    stdscr.keypad(True)

    state = {"selected": -1, "visible_items": [], "last_h": 0, "last_w": 0}
    panels = None   # initialized after first size check
    frame = 0

    while True:
        h, w = stdscr.getmaxyx()

        # Rebuild panels on resize or first run
        if h != state["last_h"] or w != state["last_w"]:
            panels = build_layout(h, w)
            for p in panels.values():
                p.dirty = True
            state["last_h"], state["last_w"] = h, w

        # Fetch data
        data = query_db(DB_PATH)
        team_data = query_teams(DB_PATH, {s["session_id"] for s in data["active_sessions"]})

        stdscr.erase()
        draw_titlebar(stdscr, w, data, team_data, frame)
        for name, panel in panels.items():
            panel.draw(stdscr, data, team_data, state, frame)
        stdscr.refresh()

        frame += 1
        ch = stdscr.getch()
        handle_input(ch, state, panels)


def build_layout(h: int, w: int) -> dict[str, Panel]:
    lw = (w * 3) // 5
    rw = w - lw

    # Rough height splits for left column
    # Adjust based on content at runtime via panel.resize()
    return {
        "teams":    TeamsPanel(   y=2,  x=0,  h=6,     w=lw),
        "sessions": SessionsPanel(y=8,  x=0,  h=h-16,  w=lw),
        "history":  HistoryPanel( y=h-8, x=0, h=8,     w=lw),
        "detail":   DetailPanel(  y=2,  x=lw, h=h-2,   w=rw),
    }
```

Panel heights are recalculated each draw cycle based on content length — panels call `self.resize()` themselves if needed.

---

## TeamsPanel content

```
╭── TEAMS  my-project · 1✓ 2● 2○ ──────────────────────────────╮
│ ├─ ◉  3m  abc123  researcher   ⣿⣷⣦⣄⣀⠀⠀⠀⠀⠀                   │
│ └─ ◉  1m  def456  implementer  ⠀⠀⠀⣀⣤⣶⣿⣿⣷⣦                   │
╰───────────────────────────────────────────────────────────────╯
```

For multiple teams, show each team's name as a sub-header inside the box.

## SessionsPanel content

```
╭── SESSIONS  2 running ────────────────────────────────────────╮
│ ◉   5m  ghi789  fix login bug         ⣿⣿⣷⣦⣄⣀⠀⠀⠀⠀             │
│    ├─ ⠋  2m  [claude-agents] debug    ⣿⣿⣿⣷⣦⣄⣀⠀⠀              │
│    └─ ⠋  1m  [claude-agents] explore  ⠀⠀⣀⣤⣶⣿⣿⣷⣦              │
│ ○  ~3m  abc123  (waiting for input)                           │
╰───────────────────────────────────────────────────────────────╯
```

## DetailPanel content

When teammate selected → task list:
```
╭── DETAIL  abc12 · my-project/researcher ──────────────────────╮
│ ● Implement auth endpoints                                    │
│ ○ Write unit tests                                            │
│ ○ Code review PR #42                                          │
│ ✓ Research API patterns                                       │
│ ○ Update docs                                                 │
╰───────────────────────────────────────────────────────────────╯
```

When subagent selected → transcript preview (same as current behavior).

When nothing selected → stats (AGENTS 7d + TOOLS 7d, same as current).

---

## Keyboard

| Key    | Action                              |
|--------|-------------------------------------|
| `j/↓`  | Select next item                    |
| `k/↑`  | Select previous item                |
| `Esc`  | Deselect (back to stats)            |
| `Enter`| Open selected in iTerm2 tab         |
| `q/Q`  | Quit                                |

---

## Implementation phases

### Phase 1 — Box drawing + theme (no behavior change)
- Add `SYMBOLS` dict
- Implement `draw_box()` helper
- Replace flat `draw()` rendering with box-bordered sections
- Verify: dashboard looks like btop visually, all data still shows

### Phase 2 — Component classes
- Extract `TeamsPanel`, `SessionsPanel`, `HistoryPanel`, `DetailPanel`
- Implement `Panel` base class with `dirty` flag
- Connect `build_layout()` + resize detection in main loop
- Verify: resize works cleanly, no jank

### Phase 3 — Braille sparklines
- Extend `query_db()` with `activity` buckets
- Implement `sparkline()` function
- Add sparklines to team member rows and session rows
- Verify: graphs animate, quiet sessions show flat line

### Phase 4 — Polish
- Dynamic panel height (panels resize based on content count)
- Narrow terminal fallback (< 80 cols: hide detail panel, inline expand)
- Footer hint updates per context

---

## Files to create/modify

| File            | Action              |
|-----------------|---------------------|
| `claude-agents` | Full rewrite in-place |
| `test-teams.sh` | No changes needed   |
| `test-agents.sh`| No changes needed   |
| `CHANGELOG.md`  | Add v0.5.0 entry after completion |

The rewrite is **entirely contained in `claude-agents`**. No new files, no new dependencies beyond stdlib.

---

## Reference: current code locations

```
query_db()        line 30    — copy verbatim, extend with activity
query_teams()     line 178   — copy verbatim
read_team_tasks() line 153   — copy verbatim
dir_tag()         line 238   — copy verbatim
find_transcript() line 246   — copy verbatim
read_preview_lines() line 284 — copy verbatim
open_agent_in_iterm2() line 315 — copy verbatim
fmt_dur()         line 339   — copy verbatim
fmt_time()        line 355   — copy verbatim
short_*()         line 364   — copy verbatim
safe_add()        line 381   — copy verbatim
draw()            line 388   — REPLACE with component system
main()            line 859   — REPLACE with new main loop
```

Source: `https://github.com/kingsotn-twelve/claude-agents/blob/main/claude-agents`

---

## Done criteria

- [ ] All panels render with `╭╮╰╯` rounded borders and embedded titles
- [ ] Braille sparklines appear on each session and team member row
- [ ] `j/k/Esc/Enter/q` all work identically to current
- [ ] TEAMS, SESSIONS, HISTORY, DETAIL panels all correct
- [ ] Terminal resize redraws cleanly with no artifacts
- [ ] `python3 -m py_compile claude-agents` passes
- [ ] `./test-agents.sh 3 3 6` shows correctly in new TUI
- [ ] `./test-teams.sh 30` shows TEAMS panel with sparklines
