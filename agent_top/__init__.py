#!/usr/bin/env python3
"""
agent-top — live terminal dashboard for Claude Code sessions & agents.
btop-style TUI with rounded box panels, braille sparklines, and tree views.
Run in a separate pane: agent-top
"""

import argparse
import curses
import glob
import random
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

VERSION = "1.2.0"

PREVIEW_ROWS = 7  # lines reserved for inline preview (divider + header + content)

DB_PATH = os.environ.get("AGENT_TOP_DB") or os.path.expanduser("~/.claude/ccnotify/ccnotify.db")

MAX_COMPLETED_AGENTS = 10
MAX_HISTORY = 20
MAX_TOOL_EVENTS = 3  # tools shown per agentless session

# ── CONSTANTS & SYMBOLS ──────────────────────────────────────

SYMBOLS = {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│", "lt": "├", "rt": "┤"}
BRAILLE = "⠀⠂⠄⠆⠈⠐⠒⠔⠖⠘⠠⠢⠤⠦⠨⠰⠲⠴⠶⠸⡀⡂⡄⡆⡈"

GREEN = CYAN = YELLOW = DIM = MAGENTA = WHITE = RED = 0

# ── TOOL NAME MAPPING ───────────────────────────────────────

TOOL_NAMES = {
    "Read": "Read file",
    "Write": "Write file",
    "Edit": "Edit file",
    "Bash": "Run command",
    "Grep": "Search code",
    "Glob": "Find files",
    "WebFetch": "Fetch URL",
    "WebSearch": "Web search",
    "AskUserQuestion": "Ask user",
    "TaskCreate": "Create task",
    "TaskUpdate": "Update task",
    "TaskList": "List tasks",
    "TaskGet": "Get task",
    "EnterWorktree": "Create worktree",
    "EnterPlanMode": "Enter plan mode",
    "ExitPlanMode": "Exit plan mode",
    "NotebookEdit": "Edit notebook",
    "SendMessage": "Send message",
    "TeamCreate": "Create team",
    "Task": "Spawn agent",
    "Skill": "Run skill",
}

VIZ_MODES = ["tree", "gantt"]
VIZ_LABELS = {"tree": "TREE", "gantt": "TIMELINE"}


def friendly_tool(name: str, label: str = "") -> str:
    """Return human-readable tool description."""
    base = TOOL_NAMES.get(name, "")
    # Handle MCP tools: mcp__server__method → Server: method
    if not base and name.startswith("mcp__"):
        parts = name.split("__")
        if len(parts) >= 3:
            server = parts[1].replace("claude_ai_", "").replace("_", " ").title()
            method = parts[2].replace("_", " ")
            base = f"{server}: {method}"
    if not base:
        base = name
    if label and label != name:
        # For tools whose label is already a human-readable description
        # (Bash description, Grep description, etc.), use the label directly
        # instead of prepending the base verb.
        # Heuristic: if the label doesn't look like a path/command fragment,
        # it's a description — use it as-is.
        if "/" in label:
            return f"{base}: {os.path.basename(label)}"
        return label
    return base
# Selection highlight variants (white-on-dark-gray)
SEL = SEL_DIM = SEL_CYAN = SEL_YELLOW = SEL_GREEN = SEL_MAGENTA = SEL_RED = 0
BG_SEL = 236  # dark gray background


def init_colors():
    global GREEN, CYAN, YELLOW, DIM, MAGENTA, WHITE, RED
    global SEL, SEL_DIM, SEL_CYAN, SEL_YELLOW, SEL_GREEN, SEL_MAGENTA, SEL_RED, BG_SEL
    curses.start_color()
    curses.use_default_colors()
    # Normal colors (pair 1-7)
    for i, c in enumerate([curses.COLOR_GREEN, curses.COLOR_WHITE, curses.COLOR_CYAN,
                           curses.COLOR_YELLOW, 8, curses.COLOR_MAGENTA, curses.COLOR_RED], 1):
        curses.init_pair(i, c, -1)
    GREEN = curses.color_pair(1) | curses.A_BOLD
    WHITE = curses.color_pair(2)
    CYAN = curses.color_pair(3) | curses.A_BOLD
    YELLOW = curses.color_pair(4) | curses.A_BOLD
    DIM = curses.color_pair(5)
    MAGENTA = curses.color_pair(6) | curses.A_BOLD
    RED = curses.color_pair(7) | curses.A_BOLD
    # Selection highlight colors (pair 11-16: foreground on dark gray)
    try:
        curses.init_pair(11, curses.COLOR_WHITE, BG_SEL)
        curses.init_pair(12, 8, BG_SEL)  # dim on dark gray
        curses.init_pair(13, curses.COLOR_CYAN, BG_SEL)
        curses.init_pair(14, curses.COLOR_YELLOW, BG_SEL)
        curses.init_pair(15, curses.COLOR_GREEN, BG_SEL)
        curses.init_pair(16, curses.COLOR_MAGENTA, BG_SEL)
        curses.init_pair(17, curses.COLOR_RED, BG_SEL)
        SEL = curses.color_pair(11) | curses.A_BOLD
        SEL_DIM = curses.color_pair(12)
        SEL_CYAN = curses.color_pair(13) | curses.A_BOLD
        SEL_YELLOW = curses.color_pair(14) | curses.A_BOLD
        SEL_GREEN = curses.color_pair(15) | curses.A_BOLD
        SEL_MAGENTA = curses.color_pair(16) | curses.A_BOLD
        SEL_RED = curses.color_pair(17) | curses.A_BOLD
    except curses.error:
        # Fallback if terminal doesn't support 256 colors
        SEL = curses.A_REVERSE | curses.A_BOLD
        SEL_DIM = curses.A_REVERSE
        SEL_CYAN = curses.A_REVERSE | curses.A_BOLD
        SEL_YELLOW = curses.A_REVERSE | curses.A_BOLD
        SEL_GREEN = curses.A_REVERSE | curses.A_BOLD
        SEL_MAGENTA = curses.A_REVERSE | curses.A_BOLD
        SEL_RED = curses.A_REVERSE | curses.A_BOLD


# ── DATA QUERIES ─────────────────────────────────────────────

STATS_RANGES = [
    ("1h", "-1 hours"),
    ("1d", "-1 days"),
    ("7d", "-7 days"),
    ("30d", "-30 days"),
    ("all", None),
]


def query_db(db_path: str, stats_range_idx: int = 2) -> dict:
    data = {
        "active_sessions": [],
        "running_agents": [],
        "completed_agents": [],
        "recent_prompts": [],
        "tool_events": {},  # session_id -> [{tool_name, tool_label}]
        "session_tools": {},  # session_id -> [{tool_name, tool_label, created_at}] — extended list for detail view
        "top_agents": [],
        "top_tools": [],
        "error_stats": [],
        "session_prompts": {},
        "activity": {},
    }
    if not os.path.exists(db_path):
        return data

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Migrate: add columns if not present (existing installs)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(prompt)")}
        if "pid" not in cols:
            conn.execute("ALTER TABLE prompt ADD COLUMN pid INTEGER")
        te_cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_event)")}
        for col, ctype in [("tool_input", "TEXT"), ("tool_response", "TEXT"), ("tool_use_id", "TEXT"), ("duration_ms", "INTEGER"), ("is_error", "INTEGER DEFAULT 0"), ("error_message", "TEXT"), ("cwd", "TEXT")]:
            if col not in te_cols:
                conn.execute(f"ALTER TABLE tool_event ADD COLUMN {col} {ctype}")

        # Active sessions: latest prompt per session, un-stopped only.
        # No time-based heuristics — we check the actual process PID below.
        for row in conn.execute(
            """SELECT p.session_id, p.prompt, p.cwd, p.created_at, p.seq, p.lastWaitUserAt, p.pid
               FROM prompt p
               INNER JOIN (
                   SELECT session_id, MAX(id) as max_id
                   FROM prompt
                   WHERE stoped_at IS NULL
                   GROUP BY session_id
               ) latest ON p.id = latest.max_id
               ORDER BY p.created_at DESC
               LIMIT 50"""
        ):
            data["active_sessions"].append(dict(row))

        # Tombstone sessions whose Claude process is no longer alive.
        # pid IS NULL means old row before this feature — fall back to 2h timeout for those.
        dead_sids = []
        for s in data["active_sessions"]:
            pid = s.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)   # signal 0 = existence check, no side effects
                except (ProcessLookupError, OSError):
                    dead_sids.append(s["session_id"])
        if dead_sids:
            conn.execute(
                f"UPDATE prompt SET stoped_at = datetime('now') WHERE session_id IN ({','.join('?'*len(dead_sids))}) AND stoped_at IS NULL",
                dead_sids,
            )
            data["active_sessions"] = [s for s in data["active_sessions"] if s["session_id"] not in dead_sids]

        # Fallback: tombstone old sessions with no pid recorded (pre-feature rows).
        conn.execute(
            """UPDATE prompt SET stoped_at = datetime('now')
               WHERE stoped_at IS NULL
                 AND pid IS NULL
                 AND created_at < datetime('now', '-2 hours')
                 AND (lastWaitUserAt IS NULL OR lastWaitUserAt < datetime('now', '-2 hours'))
                 AND session_id NOT IN (
                     SELECT DISTINCT session_id FROM tool_event
                     WHERE created_at > datetime('now', '-30 minutes')
                 )"""
        )

        # Reap orphaned agents: parent session has no open prompt rows (stoped_at IS NOT NULL
        # on all its prompts), meaning Claude fired the Stop hook and the session is truly gone.
        # This avoids reaping agents for sessions that are open but idle.
        # Grace period of 5 min covers agents whose session just started.
        conn.execute(
            """UPDATE agent SET stopped_at = datetime('now')
               WHERE stopped_at IS NULL
                 AND started_at < datetime('now', '-5 minutes')
                 AND session_id NOT IN (
                     SELECT DISTINCT session_id FROM prompt WHERE stoped_at IS NULL
                 )"""
        )
        conn.commit()

        # Running agents (skip ghosts with empty type)
        for row in conn.execute(
            """SELECT agent_id, agent_type, session_id, cwd, started_at, transcript_path
               FROM agent
               WHERE stopped_at IS NULL
               ORDER BY started_at ASC"""
        ):
            data["running_agents"].append(dict(row))

        # Completed agents (skip ghosts)
        for row in conn.execute(
            f"""SELECT agent_id, agent_type, session_id, cwd, started_at, stopped_at, transcript_path
                FROM agent
                WHERE stopped_at IS NOT NULL
                ORDER BY stopped_at DESC
                LIMIT {MAX_COMPLETED_AGENTS}"""
        ):
            data["completed_agents"].append(dict(row))

        # Recent completed prompts (skip system/task-notification noise)
        for row in conn.execute(
            f"""SELECT session_id, prompt, cwd, created_at, stoped_at, seq
                FROM prompt
                WHERE stoped_at IS NOT NULL
                  AND prompt NOT LIKE '<%'
                ORDER BY stoped_at DESC
                LIMIT {MAX_HISTORY}"""
        ):
            data["recent_prompts"].append(dict(row))

        # Tool events: last N per active session, within last 10 min
        active_sids = [s["session_id"] for s in data["active_sessions"]]
        for sid in active_sids:
            tools = []
            for row in conn.execute(
                """SELECT tool_name, tool_label FROM tool_event
                   WHERE session_id = ?
                     AND created_at > datetime('now', '-10 minutes')
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (sid, MAX_TOOL_EVENTS),
            ):
                tools.append(dict(row))
            if tools:
                # Reverse so oldest is first (left-to-right reading)
                data["tool_events"][sid] = list(reversed(tools))

        # Session tools: extended tool list per active session (for DETAIL view)
        for sid in active_sids:
            try:
                rows = []
                for row in conn.execute(
                    """SELECT tool_name, tool_label, created_at, tool_input, tool_response, duration_ms, is_error, error_message, cwd FROM tool_event
                       WHERE session_id = ?
                       ORDER BY created_at DESC
                       LIMIT 200""",
                    (sid,),
                ):
                    rows.append(dict(row))
                if rows:
                    data["session_tools"][sid] = list(reversed(rows))
            except sqlite3.OperationalError:
                pass

        # Session prompts: all prompts for active sessions (for interleaved tree view)
        data["session_prompts"] = {}
        for sid in active_sids:
            try:
                rows = []
                for row in conn.execute(
                    """SELECT prompt, created_at FROM prompt
                       WHERE session_id = ? AND prompt IS NOT NULL AND prompt != ''
                       ORDER BY created_at DESC
                       LIMIT 20""",
                    (sid,),
                ):
                    rows.append(dict(row))
                if rows:
                    data["session_prompts"][sid] = rows  # newest first
            except sqlite3.OperationalError:
                pass

        # Activity buckets for sparklines (last 60s, 20 buckets of 3s each)
        for sid in active_sids:
            try:
                rows = conn.execute(
                    "SELECT created_at FROM tool_event WHERE session_id = ? AND created_at > datetime('now', '-60 seconds')",
                    (sid,)).fetchall()
                buckets = [0] * 20
                now_utc = datetime.now(timezone.utc)
                for (ts_str,) in rows:
                    try:
                        ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                        age = (now_utc - ts).total_seconds()
                        slot = int(age / 3)
                        if 0 <= slot < 20:
                            buckets[19 - slot] += 1
                    except Exception:
                        pass
                data["activity"][sid] = buckets
            except Exception:
                pass

        # Usage stats: top agent types + top tools
        _, sql_interval = STATS_RANGES[stats_range_idx]
        if sql_interval:
            agent_where = f"WHERE started_at > datetime('now', '{sql_interval}') AND agent_type != ''"
            tool_where = f"WHERE te.created_at > datetime('now', '{sql_interval}')"
        else:
            agent_where = "WHERE agent_type != ''"
            tool_where = ""
        try:
            data["top_agents"] = [
                dict(r) for r in conn.execute(
                    f"""SELECT agent_type, cwd, COUNT(*) as cnt FROM agent
                       {agent_where}
                       GROUP BY agent_type, cwd ORDER BY cnt DESC LIMIT 12"""
                )
            ]
        except sqlite3.OperationalError:
            data["top_agents"] = []
        try:
            data["top_tools"] = [
                dict(r) for r in conn.execute(
                    f"""SELECT te.tool_name, p.cwd, COUNT(*) as cnt
                       FROM tool_event te
                       LEFT JOIN prompt p ON te.session_id = p.session_id
                       {tool_where}
                       GROUP BY te.tool_name, p.cwd ORDER BY cnt DESC LIMIT 12"""
                )
            ]
        except sqlite3.OperationalError:
            data["top_tools"] = []

        # Error stats: tools with is_error=1 grouped by tool+cwd
        try:
            error_time_filter = f"AND te.created_at > datetime('now', '{sql_interval}')" if sql_interval else ""
            data["error_stats"] = [
                dict(r) for r in conn.execute(
                    f"""SELECT te.tool_name, p.cwd, COUNT(*) as cnt
                        FROM tool_event te
                        LEFT JOIN prompt p ON te.session_id = p.session_id
                        WHERE te.is_error = 1 {error_time_filter}
                        GROUP BY te.tool_name, p.cwd
                        ORDER BY cnt DESC
                        LIMIT 8"""
                )
            ]
        except sqlite3.OperationalError:
            data["error_stats"] = []

        conn.close()
    except sqlite3.OperationalError:
        pass

    return data


def read_team_tasks(team_name: str) -> list[dict]:
    """Read task JSON files from ~/.claude/tasks/{team_name}/."""
    tasks_dir = os.path.expanduser(f"~/.claude/tasks/{team_name}")
    if not os.path.isdir(tasks_dir):
        return []
    tasks = []
    try:
        for path in glob.glob(os.path.join(tasks_dir, "*.json")):
            try:
                with open(path, "r", errors="replace") as f:
                    obj = json.load(f)
                if isinstance(obj, dict) and "status" in obj and "subject" in obj:
                    tasks.append(obj)
                elif isinstance(obj, list):
                    # Some implementations store all tasks in one file
                    for item in obj:
                        if isinstance(item, dict) and "status" in item and "subject" in item:
                            tasks.append(item)
            except Exception:
                pass
    except Exception:
        pass
    return tasks


def query_teams(db_path: str, active_session_ids: set[str]) -> dict:
    """Read team config files + task files; supplement with team_session DB table."""
    result: dict = {"teams": [], "team_session_ids": set()}
    teams_root = os.path.expanduser("~/.claude/teams")
    team_map: dict[str, dict] = {}  # team_name -> {name, members, tasks}

    # 1. Read file-system team configs
    if os.path.isdir(teams_root):
        for config_path in glob.glob(os.path.join(teams_root, "*/config.json")):
            try:
                with open(config_path, "r", errors="replace") as f:
                    cfg = json.load(f)
                team_name = cfg.get("name") or os.path.basename(os.path.dirname(config_path))
                members = []
                for m in cfg.get("members", []):
                    agent_id = m.get("agentId", "")
                    if agent_id:
                        members.append({
                            "session_id": agent_id,
                            "teammate_name": m.get("name", ""),
                            "agent_type": m.get("agentType", ""),
                        })
                        result["team_session_ids"].add(agent_id)
                tasks = read_team_tasks(team_name)
                team_map[team_name] = {"name": team_name, "members": members, "tasks": tasks}
            except Exception:
                pass

    # 2. Supplement with team_session DB table (catches teammates not yet in config files)
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT session_id, team_name, teammate_name FROM team_session"):
                sid, tname, mname = row["session_id"], row["team_name"], row["teammate_name"]
                result["team_session_ids"].add(sid)
                if tname not in team_map:
                    team_map[tname] = {"name": tname, "members": [], "tasks": []}
                # Only add member if not already in list
                existing = {m["session_id"] for m in team_map[tname]["members"]}
                if sid not in existing:
                    team_map[tname]["members"].append({
                        "session_id": sid,
                        "teammate_name": mname,
                        "agent_type": "",
                    })
            conn.close()
        except Exception:
            pass

    # 3. Filter to only teams that have at least one member active
    for team in team_map.values():
        active_members = [m for m in team["members"] if m["session_id"] in active_session_ids]
        if active_members:
            team["members"] = active_members
            result["teams"].append(team)

    return result


# ── FORMATTERS ───────────────────────────────────────────────

def dir_tag(cwd: str) -> str:
    """Return a short [dirname] prefix from a cwd path."""
    if not cwd:
        return ""
    name = os.path.basename(cwd.rstrip("/")) or os.path.basename(os.path.dirname(cwd))
    return f"[{name}]" if name else ""


def find_transcript(agent_id: str) -> str:
    uid = os.getuid()
    for pattern in [
        f"/private/tmp/claude-{uid}/**/tasks/*{agent_id}*.output",
        f"/tmp/claude-{uid}/**/tasks/*{agent_id}*.output",
        os.path.expanduser(f"~/.claude/projects/**/*{agent_id}*.jsonl"),
        os.path.expanduser(f"~/.claude/**/*{agent_id}*.jsonl"),
    ]:
        try:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return sorted(matches, key=os.path.getmtime, reverse=True)[0]
        except Exception:
            pass
    return ""


_JSONL_FMT = (
    "python3 -u -c \""
    "import sys,json\n"
    "for line in sys.stdin:\n"
    "  try:\n"
    "    e=json.loads(line)\n"
    "    t=e.get('type','')\n"
    "    if t=='assistant':\n"
    "      c=e.get('message',e).get('content',e.get('content',''))\n"
    "      if isinstance(c,list):\n"
    "        txt=''.join(b.get('text','') for b in c if b.get('type')=='text')\n"
    "      else:\n"
    "        txt=str(c)\n"
    "      if txt.strip(): print(txt,flush=True)\n"
    "    elif t=='tool_use':\n"
    "      print(f\\\"  [{e.get('name','')}]\\\",flush=True)\n"
    "  except:pass\n"
    "\""
)


def read_preview_lines(agent: dict, n: int) -> list[str]:
    """Return the last n displayable lines from an agent's output file."""
    transcript = agent.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        transcript = find_transcript(agent["agent_id"])
    if not transcript or not os.path.exists(transcript):
        return ["(no output yet)"]
    try:
        with open(transcript, "r", errors="replace") as f:
            raw = f.read()
        if transcript.endswith(".jsonl"):
            lines: list[str] = []
            for line in raw.splitlines():
                try:
                    e = json.loads(line)
                    t = e.get("type", "")
                    if t == "assistant":
                        c = e.get("message", e).get("content", e.get("content", ""))
                        txt = "".join(b.get("text", "") for b in c if b.get("type") == "text") if isinstance(c, list) else str(c)
                        lines.extend(ln for ln in txt.splitlines() if ln.strip())
                    elif t == "tool_use":
                        lines.append(f"[{e.get('name', '?')}]")
                except Exception:
                    pass
        else:
            lines = [ln for ln in raw.splitlines() if ln.strip()]
        return lines[-n:] if lines else ["(no output yet)"]
    except Exception as exc:
        return [f"(read error: {exc})"]


def open_agent_in_iterm2(agent: dict) -> str:
    transcript = agent.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        transcript = find_transcript(agent["agent_id"])
    if not transcript or not os.path.exists(transcript):
        return "no transcript found"

    if transcript.endswith(".jsonl"):
        tail_cmd = f"tail -f '{transcript}' | {_JSONL_FMT}"
    else:
        tail_cmd = f"tail -f '{transcript}'"

    script = f"""tell application "iTerm2"
  tell current window
    create tab with default profile
    tell current session of current tab
      write text "{tail_cmd}"
    end tell
  end tell
end tell"""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"iTerm2: {r.stderr.strip()[:60]}" if r.returncode != 0 else ""



def parse_dt(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to timezone-aware datetime."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fmt_dur_seconds(secs: float) -> str:
    """Format a duration in seconds to human-readable string."""
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def fmt_dur(start_str: str, end_str: str | None = None) -> str:
    try:
        start = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc) if end_str else datetime.now(timezone.utc)
        secs = max(0, int((end - start).total_seconds()))
        if secs < 60:
            return f"{secs}s"
        m, s = divmod(secs, 60)
        if m < 60:
            return f"{m}m{s:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m"
    except Exception:
        return "?"


def fmt_time(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M:%S")
    except Exception:
        return "?"


def short_id(s: str) -> str:
    return s[:7] if len(s) > 8 else s


def short_session(s: str) -> str:
    return s[:6] if len(s) > 8 else s


def short_prompt(p: str | None, maxlen: int = 40) -> str:
    if not p:
        return ""
    p = p.replace("\n", " ").strip()
    if p.startswith("<"):
        return ""
    return p[:maxlen] + ".." if len(p) > maxlen else p


def safe_add(stdscr, row: int, col: int, text: str, width: int, attr=0):
    try:
        stdscr.addnstr(row, col, text, max(0, width - col), attr)
    except curses.error:
        pass


# ── BRAILLE GRAPH ────────────────────────────────────────────

def sparkline(buckets, width=10):
    n = width * 2
    vals = ([0] * max(0, n - len(buckets)) + buckets)[-n:]
    mx = max(vals) if vals else 0
    if mx == 0:
        return BRAILLE[0] * width
    norm = [min(4, int(v / mx * 4.99)) if v > 0 else 0 for v in vals]
    return "".join(BRAILLE[norm[i] * 5 + norm[i + 1]] for i in range(0, n, 2))


# ── GAME OF LIFE ─────────────────────────────────────────────

def life_init(rows, cols, density=0.3):
    """Random seed for Game of Life grid."""
    return [[random.random() < density for _ in range(cols)] for _ in range(rows)]


def life_step(grid, rows, cols):
    """One generation of Conway's Game of Life (toroidal, optimized)."""
    new = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        rm = (r - 1) % rows
        rp = (r + 1) % rows
        row_m, row_0, row_p = grid[rm], grid[r], grid[rp]
        for c in range(cols):
            cm = (c - 1) % cols
            cp = (c + 1) % cols
            n = row_m[cm] + row_m[c] + row_m[cp] + row_0[cm] + row_0[cp] + row_p[cm] + row_p[c] + row_p[cp]
            if n == 3 or (n == 2 and row_0[c]):
                new[r][c] = True
    return new


def life_render(grid, rows, cols, char_w, char_h):
    """Render grid as list of [(char, density), ...] per row. Density 0-8 = alive dots per braille cell."""
    lines = []
    for cy in range(char_h):
        row = []
        for cx in range(char_w):
            code = 0x2800
            alive = 0
            for dy in range(4):
                for dx in range(2):
                    gr, gc = cy * 4 + dy, cx * 2 + dx
                    if gr < rows and gc < cols and grid[gr][gc]:
                        alive += 1
                        if dx == 0:
                            code |= 1 << [0, 1, 2, 6][dy]
                        else:
                            code |= 1 << [3, 4, 5, 7][dy]
            row.append((chr(code), alive))
        lines.append(row)
    return lines


# ── VISUALIZATION MODES ──────────────────────────────────────


def _build_gantt_segments(prompts, tools, agents, now_utc):
    """Build compressed active-time segments for flame graph Gantt.

    Each prompt defines a segment. Active time runs from prompt start to
    last tool/agent activity in that window. Idle gaps between prompts
    are compressed out.

    Returns (segments, total_active_s).
    """
    sorted_prompts = sorted(prompts, key=lambda p: p.get("created_at", ""))
    if not sorted_prompts:
        return [], 0.0

    segments = []
    cumulative_offset = 0.0

    for i, p in enumerate(sorted_prompts):
        seg_start = parse_dt(p.get("created_at"))
        if not seg_start:
            continue

        # Window end: next prompt start, or now
        if i + 1 < len(sorted_prompts):
            window_end = parse_dt(sorted_prompts[i + 1].get("created_at")) or now_utc
        else:
            window_end = now_utc

        # Find last activity in this window
        last_activity = seg_start

        for t in tools:
            t_start = parse_dt(t.get("created_at"))
            if not t_start or t_start < seg_start or t_start >= window_end:
                continue
            t_end = t_start
            dur_ms = t.get("duration_ms")
            if dur_ms:
                t_end = t_start + timedelta(milliseconds=dur_ms)
            last_activity = max(last_activity, t_end)

        for a in agents:
            a_start = parse_dt(a.get("started_at"))
            a_stop = parse_dt(a.get("stopped_at"))
            if not a_start or a_start >= window_end or (a_stop and a_stop <= seg_start):
                continue
            effective_end = min(a_stop or now_utc, window_end)
            last_activity = max(last_activity, effective_end)

        # Skip segments with no real activity (no tools/agents fired)
        if last_activity == seg_start:
            continue

        seg_end = min(last_activity, window_end)
        duration_s = max(1.0, (seg_end - seg_start).total_seconds())

        segments.append({
            "prompt_text": short_prompt(p.get("prompt", ""), 20),
            "start": seg_start,
            "end": seg_start + timedelta(seconds=duration_s),
            "duration_s": duration_s,
            "offset_s": cumulative_offset,
        })
        cumulative_offset += duration_s

    return segments, cumulative_offset


def _time_to_col(dt_val, segments, total_active_s, bar_w):
    """Map an absolute datetime to an x-column on the compressed timeline."""
    if not segments or total_active_s <= 0:
        return 0
    for seg in segments:
        if seg["start"] <= dt_val <= seg["end"]:
            local_frac = (dt_val - seg["start"]).total_seconds() / max(0.001, seg["duration_s"])
            global_frac = (seg["offset_s"] + local_frac * seg["duration_s"]) / total_active_s
            return min(bar_w - 1, int(global_frac * bar_w))
    # Falls in an idle gap — snap to nearest segment boundary
    for seg in segments:
        if dt_val < seg["start"]:
            global_frac = seg["offset_s"] / total_active_s
            return min(bar_w - 1, int(global_frac * bar_w))
    return bar_w - 1

def _draw_viz_gantt(stdscr, y, x, h, w, cache, state):
    """Flame graph Gantt: compressed active-time horizontal bars for the entire session."""
    active_all = cache.get("active_all", [])
    r_agents = cache.get("r_agents", [])
    c_agents = cache.get("c_agents", [])
    session_tools = cache.get("session_tools", {})
    session_prompts = cache.get("session_prompts", {})
    rw = x + w - 1

    # Scope to selected session
    vis = state.get("visible_items", [])
    sel = state.get("selected", -1)
    sel_item = vis[sel] if 0 <= sel < len(vis) else None
    target_sid = sel_item.get("session_id", "") if sel_item else ""
    if not target_sid and active_all:
        target_sid = active_all[0]["session_id"]
    if not target_sid:
        safe_add(stdscr, y + 1, x + 2, "select a session", rw, DIM)
        return

    # Gather data
    prompts = session_prompts.get(target_sid, [])
    tools = session_tools.get(target_sid, [])
    all_agents = [a for a in (r_agents + c_agents) if a.get("session_id") == target_sid]
    now_utc = datetime.now(timezone.utc)

    segments, total_active_s = _build_gantt_segments(prompts, tools, all_agents, now_utc)
    if not segments:
        safe_add(stdscr, y + 1, x + 2, "(no activity)", rw, DIM)
        return

    # Layout
    label_w = 16
    bar_w = w - label_w - 12  # room for label + bar + duration
    if bar_w < 8:
        return
    bar_x = x + label_w + 2

    pr = y

    # Row 0: Header — active time (wall time)
    active_str = fmt_dur_seconds(total_active_s)
    wall_s = (segments[-1]["end"] - segments[0]["start"]).total_seconds()
    wall_str = fmt_dur_seconds(wall_s)
    header = f"active {active_str}"
    if wall_s > total_active_s * 1.1:
        header += f"  ({wall_str} wall)"
    safe_add(stdscr, pr, x + 2, header, rw, DIM)
    pr += 1

    # Row 1: Prompt markers — thin verticals with numbers
    marker_line = list(" " * bar_w)
    for i, seg in enumerate(segments):
        col = _time_to_col(seg["start"], segments, total_active_s, bar_w)
        num = str(i + 1)
        if 0 <= col < bar_w:
            marker_line[col] = "\u258f"  # ▏
            # Place number after marker if room
            for j, ch in enumerate(num):
                if col + 1 + j < bar_w:
                    marker_line[col + 1 + j] = ch
    safe_add(stdscr, pr, x + 2, "prompts".ljust(label_w), rw, DIM)
    safe_add(stdscr, pr, bar_x, "".join(marker_line)[:bar_w], rw, CYAN)
    pr += 1

    # Agent tracks: sorted by start time
    running_ids = {a["agent_id"] for a in r_agents}
    tracks = []
    for a in sorted(all_agents, key=lambda a: a.get("started_at", "")):
        running = a["agent_id"] in running_ids
        a_start = parse_dt(a.get("started_at"))
        a_end = parse_dt(a.get("stopped_at")) if a.get("stopped_at") else now_utc
        if not a_start:
            continue
        tracks.append({
            "label": (a.get("agent_type") or "agent")[:label_w],
            "start": a_start,
            "end": a_end,
            "running": running,
        })

    # Scrollable agent rows
    pinned_rows = 3  # header + markers + axis
    agent_rows = max(1, h - pinned_rows)
    scroll = state.get("detail_scroll", 0)
    scroll = min(scroll, max(0, len(tracks) - agent_rows))
    state["detail_scroll"] = scroll
    visible_tracks = tracks[scroll:scroll + agent_rows]

    for track in visible_tracks:
        if pr >= y + h - 1:
            break
        color = MAGENTA if track["running"] else DIM
        safe_add(stdscr, pr, x + 2, track["label"][:label_w].ljust(label_w), rw, color)

        col_start = _time_to_col(track["start"], segments, total_active_s, bar_w)
        col_end = _time_to_col(track["end"], segments, total_active_s, bar_w)
        col_end = max(col_start + 1, col_end)

        bar = "\u2591" * col_start + "\u2588" * (col_end - col_start)
        if track["running"] and len(bar) > 0:
            bar = bar[:-1] + "\u2593"  # ▓ pulse at trailing edge
        bar += "\u2591" * max(0, bar_w - len(bar))
        safe_add(stdscr, pr, bar_x, bar[:bar_w], rw, color)

        # Duration
        dur = fmt_dur(track["start"].isoformat(), track["end"].isoformat() if not track["running"] else None)
        if track["running"]:
            dur = "\u25c6 " + dur  # ◆
        safe_add(stdscr, pr, bar_x + bar_w + 1, dur, rw, DIM)
        pr += 1

    # Scroll indicator
    if len(tracks) > agent_rows:
        indicator = f"({scroll+1}-{min(scroll+len(visible_tracks), len(tracks))}/{len(tracks)})"
        safe_add(stdscr, pr, x + 2, indicator, rw, DIM)
        pr += 1

    # Prompt list below agents (if room)
    if pr < y + h - 2:
        safe_add(stdscr, pr, x + 2, "\u2500" * (w - 4), rw, DIM)  # ─ separator
        pr += 1
    for i, seg in enumerate(segments):
        if pr >= y + h - 1:
            break
        num = f"#{i+1}"
        prompt_text = seg.get("prompt_text") or ""
        dur = fmt_dur_seconds(seg["duration_s"])
        line = f"{num:>3} {dur:>6}  {prompt_text}"
        safe_add(stdscr, pr, x + 2, line[:w - 4], rw, DIM)
        pr += 1

    # Time axis (last row)
    axis_row = y + h - 1
    if axis_row > pr - 1:
        axis_chars = list("\u2500" * bar_w)  # ─
        marks = [0, bar_w // 4, bar_w // 2, 3 * bar_w // 4, bar_w - 1]
        for m in marks:
            frac = m / max(1, bar_w - 1)
            secs = int(frac * total_active_s)
            label = fmt_dur_seconds(secs)
            for j, ch in enumerate(label):
                if m + j < bar_w:
                    axis_chars[m + j] = ch
        safe_add(stdscr, axis_row, bar_x, "".join(axis_chars)[:bar_w], rw, DIM)


def _format_smart_summary(tool_name, raw_response, max_lines=8, max_width=70):
    """Parse tool response into a smart summary based on tool type."""
    if not raw_response:
        return ["(no response)"]
    try:
        resp = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
    except Exception:
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
        flat = resp_str.replace("\n", " ")
        result = [flat[i:i+max_width] for i in range(0, min(len(flat), max_width * max_lines), max_width)][:max_lines]

    return result[:max_lines] if result else ["(empty)"]


def _render_tool_expansion(stdscr, ev, pr, col, rw, max_row, is_error=False):
    """Render expanded tool detail lines. Returns number of rows consumed."""
    color = RED if is_error else DIM
    resp_color = RED if is_error else GREEN
    separator = "\u254c" * min(55, rw - col - 2)
    rows_drawn = 0
    max_width = rw - col - 4

    def draw(row, text, c):
        nonlocal rows_drawn, pr
        if row < max_row:
            safe_add(stdscr, row, col, text[:max_width + 4], rw, c)
            rows_drawn += 1

    # Top separator
    draw(pr, f"  {separator}", color)
    pr += 1

    # Input section — pretty-printed JSON
    raw_input = ev.get("_raw_input")
    if raw_input:
        try:
            ti = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
            pretty = json.dumps(ti, indent=2, ensure_ascii=False)
            for line in pretty.split("\n")[:12]:
                draw(pr, f"  {line[:max_width]}", color)
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
            draw(pr, f"  \u2192 {line}", resp_color)
            pr += 1

    # Bottom separator
    draw(pr, f"  {separator}", color)
    rows_drawn += 1

    return rows_drawn


def _match_tools_to_agents(tools, agents, target_sid):
    """Match tool_events to agents by session_id + time window + cwd.

    Returns:
        agent_tools: dict[agent_id] -> [tool_event_dicts]  (tools belonging to each agent)
        agent_labels: dict[agent_id] -> str  (human-readable label from the Task tool call)
        unmatched: [tool_event_dicts]  (tools not assigned to any agent)
    """
    # Only match tool events, not prompts or other kinds
    tools = [t for t in tools if t.get("kind") == "tool"]

    # Build agent time windows for this session
    session_agents = [a for a in agents if a.get("session_id") == target_sid]
    if not session_agents:
        return {}, {}, tools

    agent_tools = {a["agent_id"]: [] for a in session_agents}
    agent_labels = {}
    unmatched = []

    # Pair Task tool_events to agents 1:1 by timestamp proximity + type hint.
    # Task fires just before SubagentStart; once matched, remove from pool.
    from datetime import datetime as _dt
    task_pool = [t for t in tools if t.get("_tool_name") == "Task"]
    # Sort agents by start time so earliest agents match earliest Tasks
    sorted_agents = sorted(session_agents, key=lambda a: a.get("started_at", ""))
    used_tasks = set()
    for agent in sorted_agents:
        a_start = agent.get("started_at", "")
        a_type = agent.get("agent_type", "")
        best_task = None
        best_score = (6, 0)  # (delta_seconds, type_match_bonus) — lower delta + higher bonus wins
        for i, tt in enumerate(task_pool):
            if i in used_tasks:
                continue
            tt_ts = tt.get("ts", "")
            if not tt_ts or not a_start or tt_ts > a_start:
                continue
            try:
                t1 = _dt.fromisoformat(tt_ts.replace("Z", "+00:00")) if "T" in tt_ts else _dt.strptime(tt_ts, "%Y-%m-%d %H:%M:%S")
                t2 = _dt.fromisoformat(a_start.replace("Z", "+00:00")) if "T" in a_start else _dt.strptime(a_start, "%Y-%m-%d %H:%M:%S")
                delta = abs((t2 - t1).total_seconds())
            except Exception:
                continue
            if delta >= best_score[0] and best_task is not None:
                continue
            # Type hint: Task description often contains agent_type
            type_bonus = 1 if a_type and a_type.lower() in tt.get("text", "").lower() else 0
            score = (delta, -type_bonus)  # lower is better
            if score < best_score:
                best_score = score
                best_task = (i, tt)
        if best_task:
            idx, tt = best_task
            used_tasks.add(idx)
            agent_labels[agent["agent_id"]] = tt.get("text", agent.get("agent_type", "agent"))

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


def _draw_viz_tree(stdscr, y, x, h, w, cache, state):
    """Interleaved timeline: prompts, tools, and agents in chronological order (newest first)."""
    active_all = cache.get("active_all", [])
    r_agents = cache.get("r_agents", [])
    c_agents = cache.get("c_agents", [])
    session_tools = cache.get("session_tools", {})
    tool_events = cache.get("tool_events", {})
    session_prompts = cache.get("session_prompts", {})
    rw = x + w - 1  # absolute right edge minus border

    # Scope to selected session
    vis = state.get("visible_items", [])
    sel = state.get("selected", -1)
    sel_item = vis[sel] if 0 <= sel < len(vis) else None
    target_sid = sel_item.get("session_id", "") if sel_item else ""
    if not target_sid and active_all:
        target_sid = active_all[0]["session_id"]
    if not target_sid:
        safe_add(stdscr, y, x + 2, "select a session", rw, DIM)
        return

    # Build unified timeline: collect all events with timestamps
    timeline = []
    # Prompts
    for p in session_prompts.get(target_sid, []):
        prompt_text = (p.get("prompt") or "").replace("\n", " ").strip()
        if prompt_text.startswith("<"):
            continue
        timeline.append({"ts": p.get("created_at", ""), "kind": "prompt", "text": prompt_text})
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
            "_cwd": t.get("cwd", ""),
        })
    # Agents — variable defs only; rendered as agent_groups below
    children = [a for a in r_agents if a["session_id"] == target_sid and a.get("agent_type")]
    completed = [a for a in c_agents if a["session_id"] == target_sid and a.get("agent_type")][:5]

    # Match tools to agents
    all_agents = r_agents + c_agents
    agent_tools, agent_labels, unmatched_tools = _match_tools_to_agents(timeline, all_agents, target_sid)

    # Build agent group events with disambiguation for duplicate labels
    agent_group_events = []
    all_agent_list = children + completed
    # Count label occurrences to decide whether to add sequence numbers
    raw_labels = []
    for a in all_agent_list:
        raw_labels.append(agent_labels.get(a["agent_id"], a["agent_type"]))
    label_counts = {}
    for lbl in raw_labels:
        label_counts[lbl] = label_counts.get(lbl, 0) + 1
    label_seq = {}  # track next sequence number per label
    for i, a in enumerate(all_agent_list):
        aid = a["agent_id"]
        a_tools = agent_tools.get(aid, [])
        adur = fmt_dur(a["started_at"], a.get("stopped_at"))
        running = a in children
        label = raw_labels[i]
        # Add sequence number when label appears more than once
        if label_counts.get(label, 1) > 1:
            seq = label_seq.get(label, 1)
            label_seq[label] = seq + 1
            display_label = f"{label} #{seq}"
        else:
            display_label = label
        agent_group_events.append({
            "ts": a.get("started_at", ""),
            "kind": "agent_group",
            "text": f"{display_label}  {adur}",
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
                        timeline.append(child)
                        if not is_collapsed:
                            for agent_tool in child.get("_children", []):
                                agent_tool["_under_agent"] = True
                                timeline.append(agent_tool)
                    else:
                        timeline.append(child)
        else:
            timeline.extend(prompt_children)

    # Tag each event with its prompt group index so we can dim non-active groups
    group_idx = -1
    for ev in timeline:
        if ev.get("kind") == "prompt":
            group_idx += 1
        ev["_group"] = group_idx

    # Store timeline so Enter can access the highlighted item
    state["_tree_len"] = len(timeline)
    state["_tree_timeline"] = timeline

    # Reposition cursor to anchored prompt after expand/collapse
    anchor = state.pop("_cursor_anchor", None)
    if anchor:
        for i, ev in enumerate(timeline):
            if ev.get("_prompt_key") == anchor:
                state["tree_cursor"] = i
                break

    cursor = state.get("tree_cursor", 0)
    if cursor >= len(timeline):
        cursor = max(0, len(timeline) - 1)
        state["tree_cursor"] = cursor

    # Estimate expansion rows for scroll calculation
    expanded_idx = state.get("_expanded_tool", -1)
    expansion_height = 12 if 0 <= expanded_idx < len(timeline) else 0
    visible_rows = max(1, h - expansion_height)
    scroll = state.get("detail_scroll", 0)
    if cursor < scroll:
        scroll = cursor
    elif cursor >= scroll + visible_rows:
        scroll = cursor - visible_rows + 1
    state["detail_scroll"] = scroll
    visible = timeline[scroll:scroll + visible_rows]

    pr = y
    kind_colors = {"prompt": WHITE, "tool": YELLOW, "agent": MAGENTA, "agent_group": MAGENTA}
    kind_icons = {"prompt": "\u25b8", "tool": "\u2502", "agent": "\u25c6", "agent_group": "\u25c6"}
    focused = state.get("focus") == "right"

    # Find which group the cursor belongs to
    cursor_group = -1
    if 0 <= cursor < len(timeline):
        cursor_group = timeline[cursor].get("_group", -1)

    for i, ev in enumerate(visible):
        if pr >= y + h:
            break
        idx = scroll + i
        is_cursor = focused and idx == cursor
        kind = ev["kind"]
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
        in_active_group = focused and ev.get("_group") == cursor_group
        if in_active_group or is_cursor:
            color = kind_colors.get(kind, DIM)
            if kind == "agent" and not ev.get("running"):
                color = DIM
        else:
            color = DIM

        # Error override
        is_err = ev.get("_is_error", False)
        if is_err and kind == "tool":
            icon = "\u2717"  # cross mark
            color = RED

        ts = fmt_time(ev.get("ts", ""))
        # Indent: prompt=0, agent_group/tool=2, tool-under-agent=4
        if kind == "prompt":
            indent = 0
        elif ev.get("_under_agent"):
            indent = 4
        else:
            indent = 2
        col_start = x + 2 + indent
        icon_col = x + 11 + indent
        text_w = w - 15 - indent  # available width for text after icon (minus borders)
        text = ev["text"]
        if suffix and kind in ("prompt", "agent_group") and ev.get("_collapsed"):
            text = text[:text_w - len(suffix)] + suffix

        if kind == "prompt" and not ev.get("_collapsed") and len(text) > text_w:
            # Wrap prompt across multiple lines
            lines = []
            while text and len(lines) < 4:  # max 4 lines
                lines.append(text[:text_w])
                text = text[text_w:]
            for li, line in enumerate(lines):
                if pr >= y + h:
                    break
                if li == 0:
                    if is_cursor:
                        safe_add(stdscr, pr, x + 1, " " * (w - 2), rw, curses.A_REVERSE)
                        safe_add(stdscr, pr, col_start, ts, rw, DIM | curses.A_REVERSE)
                        safe_add(stdscr, pr, icon_col, f"{icon} {line}", rw, color | curses.A_REVERSE)
                    else:
                        safe_add(stdscr, pr, col_start, ts, rw, DIM)
                        safe_add(stdscr, pr, icon_col, f"{icon} {line}", rw, color)
                else:
                    attr = (color | curses.A_REVERSE) if is_cursor else color
                    if is_cursor:
                        safe_add(stdscr, pr, x + 1, " " * (w - 2), rw, curses.A_REVERSE)
                    safe_add(stdscr, pr, icon_col + 2, line, rw, attr)
                pr += 1
        else:
            text = text[:text_w]
            if is_cursor:
                safe_add(stdscr, pr, x + 1, " " * (w - 2), rw, curses.A_REVERSE)
                safe_add(stdscr, pr, col_start, ts, rw, DIM | curses.A_REVERSE)
                safe_add(stdscr, pr, icon_col, f"{icon} {text}", rw, color | curses.A_REVERSE)
            else:
                safe_add(stdscr, pr, col_start, ts, rw, DIM)
                safe_add(stdscr, pr, icon_col, f"{icon} {text}", rw, color)
            pr += 1
            # Render expansion if this tool is expanded
            if kind == "tool" and state.get("_expanded_tool") == idx:
                expansion_rows = _render_tool_expansion(
                    stdscr, ev, pr, col_start, rw, y + h,
                    is_error=ev.get("_is_error", False)
                )
                pr += expansion_rows

    if not timeline:
        safe_add(stdscr, y, x + 2, "(no activity)", rw, DIM)


def _draw_viz_graph_removed():
    """Removed — was flow graph. Kept as placeholder to avoid index issues."""
    pass


def _unused_graph():
    active_all = cache.get("active_all", [])
    rw_abs = x + w - 1

    # Pick session
    vis = state.get("visible_items", [])
    sel = state.get("selected", -1)
    sel_item = vis[sel] if 0 <= sel < len(vis) else None
    target_sid = sel_item.get("session_id", "") if sel_item else ""
    if not target_sid and active_all:
        target_sid = active_all[0]["session_id"]
    if not target_sid:
        safe_add(stdscr, y + 1, x + 2, "select a session", rw_abs, DIM)
        return

    # Query conversation turns (cached per session, refreshed with data)
    graph_cache = state.setdefault("_graph_cache", {})
    cache_key = f"{target_sid}:{frame // DATA_FRAMES}"  # refresh with data cycle
    if graph_cache.get("key") != cache_key:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            prompts = conn.execute(
                "SELECT prompt, created_at, seq FROM prompt WHERE session_id = ? ORDER BY seq ASC LIMIT 10",
                (target_sid,)
            ).fetchall()
            agents = conn.execute(
                "SELECT agent_id, agent_type, started_at, stopped_at FROM agent WHERE session_id = ? ORDER BY started_at ASC",
                (target_sid,)
            ).fetchall()
            tools = conn.execute(
                "SELECT tool_name, tool_label, created_at FROM tool_event WHERE session_id = ? ORDER BY created_at ASC LIMIT 50",
                (target_sid,)
            ).fetchall()
            conn.close()
            graph_cache.update({"key": cache_key, "prompts": [dict(r) for r in prompts],
                                "agents": [dict(r) for r in agents], "tools": [dict(r) for r in tools]})
        except Exception:
            safe_add(stdscr, y + 1, x + 2, "(db error)", rw_abs, DIM)
            return
    prompts = graph_cache.get("prompts", [])
    agents = graph_cache.get("agents", [])
    tools = graph_cache.get("tools", [])

    if not prompts:
        safe_add(stdscr, y + 1, x + 2, f"session {target_sid[:7]}: no data", rw_abs, DIM)
        return

    # Build layers: assign agents and tools to their prompt turn by timestamp
    layers = []
    for pi, p in enumerate(prompts):
        turn_start = p["created_at"]
        turn_end = prompts[pi + 1]["created_at"] if pi + 1 < len(prompts) else "9999-12-31"
        turn_agents = []
        for a in agents:
            if turn_start <= a["started_at"] < turn_end:
                atype = a["agent_type"] or "agent"
                # Tools used by this agent (approximate: tools during agent lifetime)
                a_start = a["started_at"]
                a_end = a["stopped_at"] or "9999-12-31"
                a_tools = [friendly_tool(t["tool_name"], t["tool_label"])
                           for t in tools if a_start <= t["created_at"] <= a_end]
                turn_agents.append({"type": atype, "tools": a_tools[:3]})
        # Direct tools (not during any agent)
        direct_tools = []
        for t in tools:
            if turn_start <= t["created_at"] < turn_end:
                in_agent = any(a["started_at"] <= t["created_at"] <= (a["stopped_at"] or "9999-12-31") for a in agents)
                if not in_agent:
                    direct_tools.append(friendly_tool(t["tool_name"], t["tool_label"]))
        prompt_text = short_prompt(p["prompt"], w - 8) or f"turn {p['seq']}"
        layers.append({"prompt": prompt_text, "agents": turn_agents, "tools": direct_tools[:3]})

    # Build flat node list for hover navigation
    graph_nodes = []  # [{type, label, detail, row, col}]
    for li, layer in enumerate(layers):
        graph_nodes.append({"type": "prompt", "label": layer["prompt"],
                            "detail": f"Turn {li + 1}: {layer['prompt']}", "layer": li})
        for a in layer["agents"]:
            tools_str = ", ".join(a["tools"][:5]) if a["tools"] else "(no tools)"
            graph_nodes.append({"type": "agent", "label": a["type"],
                                "detail": f"{a['type']}: {tools_str}", "layer": li})
            for t in a["tools"]:
                graph_nodes.append({"type": "tool", "label": t,
                                    "detail": t, "layer": li})
        for t in layer["tools"]:
            graph_nodes.append({"type": "tool", "label": t, "detail": t, "layer": li})
    state["graph_nodes"] = graph_nodes

    # Hover index
    hover = state.get("graph_hover", 0)
    if graph_nodes:
        hover = max(0, min(hover, len(graph_nodes) - 1))
        state["graph_hover"] = hover

    # Render top-to-bottom flow
    pr = y
    mid = x + w // 2
    type_icons = {"prompt": "\u25c9", "agent": "\u25c8", "tool": "\u25cb"}
    node_idx = 0  # tracks position in graph_nodes

    for li, layer in enumerate(layers):
        if pr >= y + h - 1:
            break

        # Prompt node (centered)
        plabel = layer["prompt"][:w - 6]
        px = mid - len(plabel) // 2 - 1
        is_hov = (node_idx == hover)
        pcolor = (CYAN | curses.A_BOLD) if is_hov else GREEN
        safe_add(stdscr, pr, px, f"\u25c9 {plabel}", rw_abs, pcolor)
        if is_hov:
            safe_add(stdscr, pr, x + 2, "\u25b6", rw_abs, CYAN)
        prompt_row = pr
        pr += 1
        node_idx += 1

        # Fan-out: agents + direct tools spread horizontally
        children = []
        for a in layer["agents"]:
            children.append(("agent", a["type"], a["tools"]))
        for t in layer["tools"]:
            children.append(("tool", t, []))

        if children and pr < y + h - 1:
            n_kids = len(children)
            spacing = max(1, (w - 8) // max(n_kids, 1))
            start_x = x + 4

            for ci, (ctype, clabel, ctools) in enumerate(children):
                if pr >= y + h - 1:
                    break
                cx = start_x + ci * spacing
                icon = type_icons.get(ctype, "\u25cb")

                # Connection line from prompt
                if prompt_row + 1 == pr:
                    if cx < mid:
                        safe_add(stdscr, pr, cx, "\u2571", rw_abs, DIM)
                    elif cx > mid:
                        safe_add(stdscr, pr, cx, "\u2572", rw_abs, DIM)
                    else:
                        safe_add(stdscr, pr, cx, "\u2502", rw_abs, DIM)

                pr_child = pr + 1 if prompt_row + 1 == pr else pr
                if pr_child < y + h:
                    is_hov = (node_idx == hover)
                    color = (CYAN | curses.A_BOLD) if is_hov else (MAGENTA if ctype == "agent" else YELLOW)
                    safe_add(stdscr, pr_child, cx, f"{icon} {clabel[:spacing - 3]}", rw_abs, color)
                    if is_hov:
                        safe_add(stdscr, pr_child, x + 2, "\u25b6", rw_abs, CYAN)
                    node_idx += 1

                    # Tool leaves under agent
                    for ti, tl in enumerate(ctools):
                        if pr_child + 1 + ti >= y + h:
                            node_idx += 1
                            continue
                        conn = "\u2514" if ti == len(ctools) - 1 else "\u251c"
                        is_hov = (node_idx == hover)
                        tcolor = (CYAN | curses.A_BOLD) if is_hov else DIM
                        safe_add(stdscr, pr_child + 1 + ti, cx + 1, f"{conn} {tl[:spacing - 5]}", rw_abs, tcolor)
                        if is_hov:
                            safe_add(stdscr, pr_child + 1 + ti, x + 2, "\u25b6", rw_abs, CYAN)
                        node_idx += 1

            pr = pr_child + 1 + max((len(c[2]) for c in children), default=0)
        else:
            pr += 1

        # Convergence lines to next prompt
        if li < len(layers) - 1 and pr < y + h - 1:
            safe_add(stdscr, pr, mid, "\u2502", rw_abs, DIM)
            pr += 1

    # Legend + hover info
    if pr < y + h:
        safe_add(stdscr, y + h - 1, x + 2, "\u25c9 prompt", rw_abs, GREEN)
        safe_add(stdscr, y + h - 1, x + 13, "\u25c8 agent", rw_abs, MAGENTA)
        safe_add(stdscr, y + h - 1, x + 23, "\u25cb tool", rw_abs, YELLOW)


def _progress_bar(done, in_progress, total, width=5):
    """Build a compact progress bar: █ for done, ▓ for in_progress, ░ for remaining."""
    if total <= 0:
        return "░" * width
    filled = int(done / total * width)
    active = int(in_progress / total * width)
    # Ensure at least 1 char for in_progress if any exist
    if in_progress > 0 and active == 0 and filled < width:
        active = 1
    remaining = width - filled - active
    return "█" * filled + "▓" * active + "░" * max(0, remaining)


def member_status(activity_buckets, session):
    """Return (icon, color) based on member activity."""
    recent = activity_buckets[-5:] if activity_buckets else []
    has_recent_tools = any(b > 0 for b in recent)
    waiting = bool(session.get("lastWaitUserAt"))
    if has_recent_tools:
        return ("◉", GREEN)
    elif waiting:
        return ("○", DIM)
    else:
        return ("◎", YELLOW)


# ── BOX DRAWING ──────────────────────────────────────────────

def draw_box(stdscr, y, x, h, w, title="", title_attr=0, border_attr=0):
    if h < 2 or w < 2:
        return
    ba = border_attr or DIM
    ta = title_attr or CYAN
    top = SYMBOLS["tl"] + SYMBOLS["h"] * (w - 2) + SYMBOLS["tr"]
    if title:
        label = f" {title} "
        if len(label) + 2 < w:
            top = top[:2] + label + top[2 + len(label):]
    safe_add(stdscr, y, x, top, x + w, ba)
    if title:
        safe_add(stdscr, y, x + 2, f" {title} ", x + w, ta)
    for row in range(y + 1, y + h - 1):
        safe_add(stdscr, row, x, SYMBOLS["v"], x + w, ba)
        safe_add(stdscr, row, x + w - 1, SYMBOLS["v"], x + w, ba)
    bot = SYMBOLS["bl"] + SYMBOLS["h"] * (w - 2) + SYMBOLS["br"]
    safe_add(stdscr, y + h - 1, x, bot, x + w, ba)


# ── MAIN DRAW + LOOP ────────────────────────────────────────

def refresh_data(cache: dict, stats_range_idx: int = 2) -> dict:
    """Refresh cached dashboard data from DB + filesystem."""
    data = query_db(DB_PATH, stats_range_idx)
    data["_stats_range_idx"] = stats_range_idx
    active_all = data["active_sessions"]
    active_sids_all = {s["session_id"] for s in active_all}
    team_data = query_teams(DB_PATH, active_sids_all)
    cache.update({
        "data": data,
        "active_all": active_all,
        "r_agents": data["running_agents"],
        "c_agents": data["completed_agents"],
        "recent": data["recent_prompts"],
        "tool_events": data["tool_events"],
        "session_tools": data["session_tools"],
        "session_prompts": data["session_prompts"],
        "activity": data["activity"],
        "team_data": team_data,
        "session_lookup": {s["session_id"]: s for s in active_all},
    })
    return cache


def _detail_content_height(sel_agent, pw, cache):
    """Estimate how many content rows DETAIL needs (excluding box borders)."""
    if not sel_agent:
        return 3
    if sel_agent.get("is_session"):
        rows = 2  # header + divider
        prompt = (sel_agent.get("prompt", "") or "").replace("\n", " ").strip()
        if prompt:
            rows += 1  # prompt line
        sid = sel_agent.get("session_id", "")
        n_tools = len(cache.get("session_tools", {}).get(sid, []))
        if n_tools:
            rows += 1 + n_tools  # blank + tool lines
        return rows
    if sel_agent.get("is_teammate"):
        tasks = sel_agent.get("_tasks", [])
        return 2 + (1 if not tasks else 2 + len(tasks))  # header + divider + progress + blank + tasks
    if sel_agent.get("is_stat"):
        return 2 + 2 + 10  # header + divider + avg + recent runs/targets
    # Agent transcript — cap preview at 8
    return 2 + 8


def _draw_detail(stdscr, pr, col, max_row, max_col, sel_agent, cache, scroll=0):
    """Render DETAIL content into a region defined by (pr, col) to (max_row, max_col)."""
    pw = max_col - col  # available width
    base_pr = pr  # top of drawable area

    def P(r, c, text, attr=0):
        sr = r - scroll  # screen row after scroll
        if base_pr <= sr < max_row:
            safe_add(stdscr, sr, c, text, max_col, attr)

    # Adjust max_row for virtual space (allow pr to go beyond visible area)
    max_row_virtual = max_row + scroll

    if sel_agent and sel_agent.get("is_session"):
        # Rich session detail
        sid = sel_agent["session_id"]
        dur = fmt_dur(sel_agent.get("started_at", ""))
        sid_short = sid[:7]
        cwd = sel_agent.get("cwd", "")
        prompt_text = sel_agent.get("prompt", "")
        tag = dir_tag(cwd)
        header = f"{sid_short} \u00b7 {tag} session \u00b7 {dur}" if tag else f"{sid_short} \u00b7 session \u00b7 {dur}"
        P(pr, col, header[:pw], GREEN | curses.A_BOLD)
        pr += 1
        P(pr, col, SYMBOLS["h"] * pw, DIM)
        pr += 1

        # Prompt
        if prompt_text and pr < max_row_virtual:
            display_prompt = prompt_text.replace("\n", " ").strip()
            if display_prompt.startswith("<"):
                display_prompt = "(system prompt)"
            P(pr, col, display_prompt[:pw], WHITE)
            pr += 1

        # Tool event timeline
        session_tools = cache.get("session_tools", {}).get(sid, [])
        if session_tools and pr < max_row_virtual:
            pr += 1
            for ev in session_tools:
                if pr >= max_row_virtual:
                    break
                ts = fmt_time(ev.get("created_at"))
                tool_str = friendly_tool(ev["tool_name"], ev.get("tool_label", ""))
                P(pr, col, ts, DIM)
                P(pr, col + 9, tool_str[:pw - 20], YELLOW)
                pr += 1
                # Show tool_input summary
                raw_input = ev.get("tool_input")
                if raw_input and pr < max_row_virtual:
                    try:
                        ti = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
                        # Show key fields compactly
                        parts = []
                        for k, v in list(ti.items())[:3]:
                            vs = str(v).replace("\n", " ")[:60]
                            parts.append(f"{k}={vs}")
                        input_line = "  " + "  ".join(parts)
                        P(pr, col, input_line[:pw], DIM)
                        pr += 1
                    except Exception:
                        pass
                # Show tool_response summary
                raw_resp = ev.get("tool_response")
                if raw_resp and pr < max_row_virtual:
                    try:
                        tr = json.loads(raw_resp) if isinstance(raw_resp, str) else raw_resp
                        resp_str = str(tr).replace("\n", " ")[:pw - 4]
                        P(pr, col, f"  → {resp_str}", GREEN)
                        pr += 1
                    except Exception:
                        pass

    elif sel_agent and sel_agent.get("is_teammate"):
        # Task list for selected team member
        team_name = sel_agent.get("team_name", "")
        teammate_name = sel_agent.get("teammate_name", "")
        dur = fmt_dur(sel_agent.get("started_at", ""))
        sid_short = sel_agent["agent_id"][:7]
        header = f"{sid_short} \u00b7 {team_name}/{teammate_name} \u00b7 {dur}"
        P(pr, col, header[:pw], CYAN | curses.A_BOLD)
        pr += 1
        P(pr, col, SYMBOLS["h"] * pw, DIM)
        pr += 1
        tasks_list = sel_agent.get("_tasks", [])
        sorted_tasks = sorted(
            tasks_list,
            key=lambda t: {"in_progress": 0, "pending": 1, "completed": 2}.get(t.get("status", ""), 1),
        )
        if not sorted_tasks:
            P(pr, col, "(no tasks)", DIM)
        else:
            t_done = sum(1 for t in sorted_tasks if t.get("status") == "completed")
            t_active = sum(1 for t in sorted_tasks if t.get("status") == "in_progress")
            t_blocked = sum(1 for t in sorted_tasks if t.get("status") == "pending" and t.get("blockedBy"))
            t_total = len(sorted_tasks)
            pbar = _progress_bar(t_done, t_active, t_total, 10)
            pct = int(t_done / t_total * 100) if t_total else 0
            parts = [f"{t_done} done"]
            if t_active:
                parts.append(f"{t_active} active")
            if t_blocked:
                parts.append(f"{t_blocked} blocked")
            t_pending_unblocked = t_total - t_done - t_active - t_blocked
            if t_pending_unblocked > 0:
                parts.append(f"{t_pending_unblocked} pending")
            P(pr, col, f"{pbar} {pct}%  {' \u00b7 '.join(parts)}", CYAN)
            pr += 1
            pr += 1  # blank line

            for t in sorted_tasks:
                if pr >= max_row_virtual:
                    break
                status = t.get("status", "")
                blocked = bool(t.get("blockedBy")) and status == "pending"
                if status == "completed":
                    icon = "\u2713"
                elif status == "in_progress":
                    icon = "\u25cf"
                elif blocked:
                    icon = "\u2298"
                else:
                    icon = "\u25cb"
                owner = t.get("owner", "")
                owner_tag = f"  [@{owner}]" if owner else ""
                subject = short_prompt(t.get("subject", "?"), pw - 6 - len(owner_tag))
                if status == "completed":
                    attr = DIM
                elif status == "in_progress":
                    attr = YELLOW
                elif blocked:
                    attr = RED
                else:
                    attr = WHITE
                P(pr, col, f"{icon}  {subject}{owner_tag}", attr)
                pr += 1

    elif sel_agent:
        # Live preview of selected subagent
        dur = fmt_dur(sel_agent["started_at"])
        atype = sel_agent.get("agent_type") or "agent"
        aid = sel_agent["agent_id"][:7]
        tag = dir_tag(sel_agent.get("cwd", ""))
        header = f"{aid} \u00b7 {tag} {atype} \u00b7 {dur}" if tag else f"{aid} \u00b7 {atype} \u00b7 {dur}"
        P(pr, col, header[:pw], MAGENTA | curses.A_BOLD)
        pr += 1
        P(pr, col, SYMBOLS["h"] * pw, DIM)
        pr += 1
        for line in read_preview_lines(sel_agent, max_row_virtual - pr):
            if pr >= max_row_virtual:
                break
            P(pr, col, line[:pw], WHITE)
            pr += 1

    elif sel_agent and sel_agent.get("is_stat"):
        # Stats drill-down
        kind = sel_agent.get("stat_kind", "")
        label = sel_agent.get("stat_label", "?")
        cnt = sel_agent.get("stat_count", 0)
        cwd = sel_agent.get("cwd", "")
        atype = sel_agent.get("agent_type", "")
        tag = dir_tag(cwd)

        P(pr, col, f"{label}  ({cnt} total)", CYAN | curses.A_BOLD)
        pr += 1
        P(pr, col, SYMBOLS["h"] * pw, DIM)
        pr += 1

        # Query recent instances from DB (cached per selection)
        stat_cache = cache.setdefault("_stat_drill", {})
        stat_key = f"{kind}:{atype}:{cwd}"
        if stat_cache.get("key") != stat_key:
            stat_cache["key"] = stat_key
            stat_cache["data"] = None
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                range_idx = cache.get("data", {}).get("_stats_range_idx", 2)
                _, sql_interval = STATS_RANGES[min(range_idx, len(STATS_RANGES) - 1)]
                if kind == "agent":
                    time_filter = f"AND started_at > datetime('now', '{sql_interval}')" if sql_interval else ""
                    cwd_filter = f"AND cwd = '{cwd}'" if cwd else ""
                    stat_cache["data"] = {"rows": [dict(r) for r in conn.execute(
                        f"SELECT agent_id, agent_type, cwd, started_at, stopped_at FROM agent WHERE agent_type = ? {time_filter} {cwd_filter} ORDER BY started_at DESC LIMIT 8",
                        (atype,)).fetchall()]}
                elif kind == "tool":
                    time_filter = f"AND te.created_at > datetime('now', '{sql_interval}')" if sql_interval else ""
                    cwd_filter = f"AND p.cwd = '{cwd}'" if cwd else ""
                    stat_cache["data"] = {
                        "labels": [dict(r) for r in conn.execute(
                            f"SELECT te.tool_label, COUNT(*) as cnt FROM tool_event te LEFT JOIN prompt p ON te.session_id = p.session_id WHERE te.tool_name = ? {time_filter} {cwd_filter} GROUP BY te.tool_label ORDER BY cnt DESC LIMIT 8",
                            (atype,)).fetchall()],
                        "recent": [dict(r) for r in conn.execute(
                            f"SELECT te.tool_label, te.created_at, te.session_id FROM tool_event te LEFT JOIN prompt p ON te.session_id = p.session_id WHERE te.tool_name = ? {time_filter} {cwd_filter} ORDER BY te.created_at DESC LIMIT 6",
                            (atype,)).fetchall()],
                    }
                conn.close()
            except Exception:
                stat_cache["data"] = None
        sd = stat_cache.get("data")
        if sd and kind == "agent":
            rows = sd.get("rows", [])
            if rows:
                durs = []
                for r in rows:
                    if r.get("stopped_at") and r.get("started_at"):
                        try:
                            s = datetime.fromisoformat(r["started_at"]).replace(tzinfo=timezone.utc)
                            e = datetime.fromisoformat(r["stopped_at"]).replace(tzinfo=timezone.utc)
                            durs.append((e - s).total_seconds())
                        except Exception:
                            pass
                if durs:
                    avg = int(sum(durs) / len(durs))
                    P(pr, col, f"avg duration: {avg}s", DIM)
                    pr += 1
                pr += 1
                P(pr, col, "RECENT RUNS", CYAN)
                pr += 1
                for r in rows:
                    if pr >= max_row_virtual:
                        break
                    aid = short_id(r["agent_id"])
                    dur = fmt_dur(r["started_at"], r.get("stopped_at")) if r.get("stopped_at") else fmt_dur(r["started_at"])
                    ts = fmt_time(r["started_at"])
                    running = "\u25cf" if not r.get("stopped_at") else "\u25cb"
                    P(pr, col, f"{running} {ts}  {dur:>6}  {aid}", DIM)
                    pr += 1
            else:
                P(pr, col, "(no recent runs)", DIM)
        elif sd and kind == "tool":
            label_rows = sd.get("labels", [])
            if label_rows:
                P(pr, col, "TOP TARGETS", CYAN)
                pr += 1
                max_lc = label_rows[0]["cnt"] if label_rows else 1
                for lr in label_rows:
                    if pr >= max_row_virtual:
                        break
                    tl = lr["tool_label"] or "(none)"
                    tc = lr["cnt"]
                    bw = 6
                    filled = int(tc / max_lc * bw) if max_lc > 0 else 0
                    bar = "\u2588" * filled + "\u2591" * (bw - filled)
                    P(pr, col, f"{bar} {tc:>3}  {tl[:pw - 14]}", DIM)
                    pr += 1
                pr += 1
                recent_rows = sd.get("recent", [])
                if recent_rows and pr < max_row_virtual:
                    P(pr, col, "RECENT", CYAN)
                    pr += 1
                    for rr in recent_rows:
                        if pr >= max_row_virtual:
                            break
                        ts = fmt_time(rr["created_at"])
                        tl = rr["tool_label"] or ""
                        sid = short_session(rr["session_id"])
                        P(pr, col, f"{ts}  {sid}  {tl[:pw - 18]}", DIM)
                        pr += 1
            else:
                P(pr, col, "(no recent uses)", DIM)
        else:
            P(pr, col, "(no data)", DIM)

    else:
        # Nothing selected — show keybinding hints
        P(pr, col, "j/k  select", DIM)
        pr += 1
        P(pr, col, "esc  deselect", DIM)
        pr += 1
        P(pr, col, "ret  open in iTerm2", DIM)


def draw(stdscr, frame: int, state: dict, cache: dict):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    if h < 5 or w < 30:
        safe_add(stdscr, 0, 0, "terminal too small", w, 0)
        stdscr.refresh()
        return

    spins = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
    sc = spins[frame % len(spins)]
    pulse = ("○", "◎", "●", "◎")[frame % 4]

    active_all = cache["active_all"]
    r_agents = cache["r_agents"]
    c_agents = cache["c_agents"]
    recent = cache["recent"]
    tool_events = cache["tool_events"]
    activity = cache["activity"]
    team_data = cache["team_data"]
    session_lookup = cache["session_lookup"]

    team_session_ids = team_data["team_session_ids"]
    teams = team_data["teams"]

    # Solo sessions: exclude team members (shown in TEAMS section instead)
    active = [s for s in active_all if s["session_id"] not in team_session_ids]

    # Build agents_by_session, track orphans
    active_sids = {s["session_id"] for s in active}
    agents_by_session: dict[str, list[dict]] = {}
    orphan_agents: list[dict] = []
    for a in r_agents:
        if a["session_id"] in active_sids:
            agents_by_session.setdefault(a["session_id"], []).append(a)
        else:
            orphan_agents.append(a)

    # Layout
    split = w >= 100
    lw = w // 2 if split else w
    rw = w - lw if split else 0
    rx = lw  # right panel x position

    top_agents = cache["data"].get("top_agents", [])
    top_tools = cache["data"].get("top_tools", [])
    error_stats = cache["data"].get("error_stats", [])

    # Helpers: clip to panel widths (preserve box borders)
    def L(r, c, text, attr=0):
        safe_add(stdscr, r, c, text, lw - 1, attr)

    def R(r, c, text, attr=0):
        safe_add(stdscr, r, c, text, rx + rw - 1, attr)

    # Reset visible items for keyboard nav
    visible_items: list[dict] = []
    # Track panel index ranges for border highlighting: [(y, h, first_idx, last_idx, title)]
    panel_ranges: list[tuple] = []

    n_team_members = sum(len(t["members"]) for t in teams)
    total_live = len(active) + len(r_agents) + n_team_members

    # -- Title bar (row 0-1, full width) --
    row = 0
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if total_live > 0:
        title = f" {sc} CLAUDE AGENTS"
        counts = []
        if teams:
            tm_count = n_team_members
            counts.append(f"{len(teams)} team{'s' if len(teams) != 1 else ''} \u00b7 {tm_count} active")
        if active:
            counts.append(f"{len(active)} session{'s' if len(active) != 1 else ''}")
        if r_agents:
            counts.append(f"{len(r_agents)} agent{'s' if len(r_agents) != 1 else ''}")
        count_str = f"  {' \u00b7 '.join(counts)}"
        title_attr = WHITE
    else:
        title = "   CLAUDE AGENTS"
        count_str = "  idle"
        title_attr = GREEN

    safe_add(stdscr, row, 0, title, w, title_attr)
    safe_add(stdscr, row, len(title), count_str, w, DIM)
    safe_add(stdscr, row, w - len(now) - 1, now, w, DIM)
    row += 1
    safe_add(stdscr, row, 0, SYMBOLS["h"] * w, w, DIM)
    row += 1
    content_top = row

    # -- Compute panel heights --
    # Teams panel
    n_team_subheaders = len(teams) if len(teams) > 1 else 0
    n_active_task_rows = 0
    for team in teams:
        for m in team["members"]:
            if any(t.get("owner") == m.get("teammate_name") and t.get("status") == "in_progress"
                   for t in team["tasks"]):
                n_active_task_rows += 1
    teams_h = (2 + n_team_members + n_active_task_rows + n_team_subheaders) if teams else 0

    # Sessions panel: each session gets 1 row + 1 inline tool row if it has recent tools
    n_sess_rows = 0
    for s in active:
        n_sess_rows += 1
        if s["session_id"] in tool_events:
            n_sess_rows += 1  # inline tool line
    n_sess_rows += len(orphan_agents)
    sess_h = (2 + n_sess_rows) if (active or orphan_agents) else 0

    # History + Stats share remaining left-panel space
    max_hist = 8
    remaining = max(6, h - content_top - teams_h - sess_h - 1)
    hist_h = min(2 + max_hist, remaining // 2 + remaining % 2)
    stats_lh = remaining - hist_h  # left-side stats height

    # If nothing active, show a small sessions box with idle message
    if not teams and not active and not r_agents:
        sess_h = 3
        remaining = max(6, h - content_top - sess_h - 1)
        hist_h = min(2 + max_hist, remaining // 2 + remaining % 2)
        stats_lh = remaining - hist_h

    # -- TEAMS panel --
    cr = content_top
    if teams:
        # Build title
        if len(teams) == 1:
            t0 = teams[0]
            tl = t0["tasks"]
            tdone = sum(1 for x in tl if x.get("status") == "completed")
            trinp = sum(1 for x in tl if x.get("status") == "in_progress")
            ttotal = len(tl)
            if ttotal > 0:
                bar = _progress_bar(tdone, trinp, ttotal, 5)
                tcounts = f"  {bar} {tdone}/{ttotal}"
            else:
                tcounts = ""
            box_title = f"TEAMS  {t0['name']}{tcounts}"
        else:
            box_title = f"TEAMS  {len(teams)} teams \u00b7 {n_team_members} active"

        teams_first_idx = len(visible_items)
        draw_box(stdscr, cr, 0, teams_h, lw, title=box_title)
        tr = cr + 1  # first content row inside box

        for team in teams:
            if tr >= cr + teams_h - 1:
                break
            if len(teams) > 1:
                # Sub-header per team
                tl = team["tasks"]
                tdone = sum(1 for x in tl if x.get("status") == "completed")
                trinp = sum(1 for x in tl if x.get("status") == "in_progress")
                ttotal = len(tl)
                if ttotal > 0:
                    bar = _progress_bar(tdone, trinp, ttotal, 5)
                    tcounts = f"  {bar} {tdone}/{ttotal}"
                else:
                    tcounts = ""
                L(tr, 2, f"\u25c8 {team['name']}{tcounts}", CYAN)
                tr += 1
                base = 4
            else:
                base = 2

            members = team["members"]
            for i, m in enumerate(members):
                if tr >= cr + teams_h - 1:
                    break
                is_last = (i == len(members) - 1)
                connector = "\u2514\u2500" if is_last else "\u251c\u2500"
                sess = session_lookup.get(m["session_id"], {})
                started_at = sess.get("created_at", "")
                dur = fmt_dur(started_at) if started_at else "?"
                teammate_name = m.get("teammate_name") or "teammate"
                sid_short = short_session(m["session_id"])
                item = {
                    "agent_id": m["session_id"],
                    "agent_type": teammate_name,
                    "session_id": m["session_id"],
                    "started_at": started_at,
                    "cwd": sess.get("cwd", ""),
                    "team_name": team["name"],
                    "teammate_name": teammate_name,
                    "is_teammate": True,
                    "_tasks": team["tasks"],
                }
                vidx = len(visible_items)
                visible_items.append(item)
                is_sel = (vidx == state.get("selected", -1))

                # Sparkline + status for this teammate
                spark = sparkline(activity.get(m["session_id"], []))
                s_icon, s_color = member_status(activity.get(m["session_id"], []), sess)

                if is_sel:
                    try:
                        stdscr.addnstr(tr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                    except curses.error:
                        pass
                    L(tr, base, connector, SEL_DIM)
                    L(tr, base + 3, "\u25b6", SEL_YELLOW)
                    L(tr, base + 5, f"{dur:>5}", SEL_YELLOW)
                    L(tr, base + 11, sid_short, SEL_DIM)
                    L(tr, base + 18, teammate_name, SEL)
                    L(tr, lw - 12, spark, SEL_DIM)
                else:
                    L(tr, base, connector, DIM)
                    L(tr, base + 3, s_icon, s_color)
                    L(tr, base + 5, f"{dur:>5}", YELLOW)
                    L(tr, base + 11, sid_short, DIM)
                    L(tr, base + 18, teammate_name, WHITE)
                    L(tr, lw - 12, spark, CYAN)
                tr += 1

                # Active task row under this member
                active_task = None
                for t in team["tasks"]:
                    if t.get("owner") == teammate_name and t.get("status") == "in_progress":
                        active_task = t
                        break
                if active_task and tr < cr + teams_h - 1:
                    continuation = "\u2502" if not is_last else " "
                    task_text = active_task.get("activeForm") or active_task.get("subject", "")
                    task_text = task_text[:lw - base - 10]
                    if is_sel:
                        try:
                            stdscr.addnstr(tr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                        except curses.error:
                            pass
                        L(tr, base, continuation, SEL_DIM)
                        L(tr, base + 5, "\u25cf", SEL_YELLOW)
                        L(tr, base + 7, task_text, SEL_YELLOW)
                    else:
                        L(tr, base, continuation, DIM)
                        L(tr, base + 5, "\u25cf", YELLOW)
                        L(tr, base + 7, task_text, YELLOW)
                    tr += 1

        panel_ranges.append((content_top, teams_h, teams_first_idx, len(visible_items) - 1, box_title))
        cr += teams_h

    # -- SESSIONS panel --
    if active or orphan_agents:
        n_running = sum(
            1 for s in active
            if not s.get("lastWaitUserAt") or s["session_id"] in agents_by_session
        )
        n_waiting = len(active) - n_running
        sess_counts = []
        if n_running:
            sess_counts.append(f"{n_running} running")
        if n_waiting:
            sess_counts.append(f"{n_waiting} waiting")
        if r_agents:
            sess_counts.append(f"{len(r_agents)} agent{'s' if len(r_agents) != 1 else ''}")
        sess_title = f"SESSIONS  {' \u00b7 '.join(sess_counts)}" if sess_counts else "SESSIONS"

        sess_first_idx = len(visible_items)
        draw_box(stdscr, cr, 0, sess_h, lw, title=sess_title)
        sr = cr + 1

        for s in active:
            if sr >= cr + sess_h - 1:
                break
            sid = s["session_id"]
            has_agents = sid in agents_by_session
            waiting = bool(s.get("lastWaitUserAt")) and not has_agents
            sid_short = short_session(sid)
            prompt = short_prompt(s.get("prompt"), max(10, lw - 32))
            spark = sparkline(activity.get(sid, []))

            # Make session selectable
            sess_item = {
                "agent_id": sid,
                "agent_type": "session",
                "session_id": sid,
                "started_at": s["created_at"],
                "cwd": s.get("cwd", ""),
                "is_session": True,
                "prompt": s.get("prompt", ""),
            }
            vidx = len(visible_items)
            visible_items.append(sess_item)
            is_sel = (vidx == state.get("selected", -1))

            if is_sel:
                try:
                    stdscr.addnstr(sr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                except curses.error:
                    pass
                L(sr, 2, "\u25b6", SEL_YELLOW)
                run_dur = fmt_dur(s["created_at"])
                L(sr, 4, f"{run_dur:>6}", SEL_YELLOW)
                L(sr, 11, sid_short, SEL_DIM)
                L(sr, 18, prompt, SEL)
                L(sr, lw - 12, spark, SEL_DIM)
            elif waiting:
                # Frozen clock: duration from start to when it stopped working
                frozen_dur = fmt_dur(s["created_at"], s.get("lastWaitUserAt"))
                L(sr, 2, "\u25a1", DIM)  # □ paused
                L(sr, 4, f"{frozen_dur:>6}", DIM)
                L(sr, 11, sid_short, DIM)
                L(sr, 18, prompt, DIM)
            else:
                run_dur = fmt_dur(s["created_at"])
                L(sr, 2, pulse, GREEN)
                L(sr, 4, f"{run_dur:>6}", YELLOW)
                L(sr, 11, sid_short, DIM)
                L(sr, 18, prompt, WHITE)
                L(sr, lw - 12, spark, CYAN)
            sr += 1

            # Inline tool line (most recent tool call for this session)
            if sid in tool_events and sr < cr + sess_h - 1:
                tools = tool_events[sid]
                parts = [friendly_tool(t["tool_name"], t.get("tool_label", "")) for t in tools]
                tool_line = "  ".join(parts)[:lw - 8]
                if is_sel:
                    try:
                        stdscr.addnstr(sr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                    except curses.error:
                        pass
                    L(sr, 4, "\u23bf", SEL_DIM)
                    L(sr, 6, tool_line, SEL_DIM)
                else:
                    L(sr, 4, "\u23bf", DIM)
                    L(sr, 6, tool_line, DIM)
                sr += 1

        # Orphan agents
        for a in orphan_agents:
            if sr >= cr + sess_h - 1:
                break
            dur = fmt_dur(a["started_at"])
            atype = a["agent_type"] or "agent"
            tag = dir_tag(a.get("cwd", ""))
            vidx = len(visible_items)
            visible_items.append(a)
            is_sel = (vidx == state.get("selected", -1))
            a_spark = sparkline(activity.get(a.get("session_id", ""), []))

            if is_sel:
                try:
                    stdscr.addnstr(sr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                except curses.error:
                    pass
                L(sr, 2, "\u25b6", SEL_YELLOW)
                L(sr, 4, f"{dur:>6}", SEL_YELLOW)
                col = 11
                if tag:
                    L(sr, col, tag, SEL_CYAN)
                    col += len(tag) + 1
                L(sr, col, atype, SEL)
                L(sr, col + len(atype) + 1, short_id(a["agent_id"]), SEL_DIM)
                L(sr, lw - 12, a_spark, SEL_DIM)
            else:
                L(sr, 2, sc, MAGENTA)
                L(sr, 4, f"{dur:>6}", YELLOW)
                col = 11
                if tag:
                    L(sr, col, tag, CYAN)
                    col += len(tag) + 1
                L(sr, col, atype, MAGENTA)
                L(sr, col + len(atype) + 1, short_id(a["agent_id"]), DIM)
                L(sr, lw - 12, a_spark, CYAN)
            sr += 1

        panel_ranges.append((cr, sess_h, sess_first_idx, len(visible_items) - 1, sess_title))
        cr += sess_h

    elif not teams:
        # No active sessions or agents — show idle box
        draw_box(stdscr, cr, 0, sess_h, lw, title="SESSIONS")
        L(cr + 1, 2, "no active sessions or agents", DIM)
        cr += sess_h

    # -- HISTORY or DETAIL-inline panel --
    # When something is selected and terminal is too narrow for side-by-side,
    # show DETAIL in the HISTORY panel's space instead.
    sel_idx = state.get("selected", -1)
    sel_agent = visible_items[sel_idx] if 0 <= sel_idx < len(visible_items) else None
    show_inline_detail = sel_agent is not None and not split

    hist_first_idx = len(visible_items)
    if show_inline_detail:
        draw_box(stdscr, cr, 0, hist_h, lw, title="DETAIL")
        _draw_detail(stdscr, cr + 1, 2, cr + hist_h - 1, lw - 1,
                     sel_agent, cache)
    else:
        draw_box(stdscr, cr, 0, hist_h, lw, title="HISTORY")
        hr = cr + 1

        history = []
        for a in c_agents:
            history.append(("agent", a["stopped_at"], a))
        for s in recent:
            history.append(("prompt", s["stoped_at"], s))
        history.sort(key=lambda x: x[1] or "", reverse=True)

        if not history:
            L(hr, 2, "(empty)", DIM)
        else:
            shown = 0
            for kind, ts, item in history:
                if hr >= cr + hist_h - 1 or shown >= max_hist:
                    break
                t = fmt_time(ts)
                if kind == "agent":
                    dur = fmt_dur(item["started_at"], item["stopped_at"])
                    atype = item.get("agent_type") or "agent"
                    hist_item = {
                        "agent_id": item.get("agent_id", ""),
                        "agent_type": atype,
                        "session_id": item.get("session_id", ""),
                        "started_at": item.get("started_at", ""),
                        "cwd": item.get("cwd", ""),
                        "is_history": True,
                        "kind": "agent",
                        "stopped_at": item.get("stopped_at", ""),
                        "transcript_path": item.get("transcript_path", ""),
                    }
                elif kind == "prompt":
                    dur = fmt_dur(item["created_at"], item["stoped_at"])
                    prompt = short_prompt(item.get("prompt"), max(10, lw - 21))
                    if not prompt:
                        continue
                    hist_item = {
                        "agent_id": item.get("session_id", ""),
                        "agent_type": "session",
                        "session_id": item.get("session_id", ""),
                        "started_at": item.get("created_at", ""),
                        "cwd": item.get("cwd", ""),
                        "is_history": True,
                        "is_session": True,
                        "kind": "prompt",
                        "prompt": item.get("prompt", ""),
                    }
                else:
                    continue

                vidx = len(visible_items)
                visible_items.append(hist_item)
                is_sel = (vidx == state.get("selected", -1))

                if kind == "agent":
                    if is_sel:
                        try:
                            stdscr.addnstr(hr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                        except curses.error:
                            pass
                        L(hr, 2, t, SEL_DIM)
                        L(hr, 11, f"{dur:>6}", SEL_DIM)
                        L(hr, 18, f"\u25b8 {atype}", SEL_MAGENTA)
                    else:
                        L(hr, 2, t, DIM)
                        L(hr, 11, f"{dur:>6}", DIM)
                        L(hr, 18, f"\u25b8 {atype}", curses.color_pair(6))
                else:
                    if is_sel:
                        try:
                            stdscr.addnstr(hr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                        except curses.error:
                            pass
                        L(hr, 2, t, SEL_DIM)
                        L(hr, 11, f"{dur:>6}", SEL_DIM)
                        L(hr, 18, prompt, SEL)
                    else:
                        L(hr, 2, t, DIM)
                        L(hr, 11, f"{dur:>6}", DIM)
                        L(hr, 18, prompt, DIM)
                hr += 1
                shown += 1

    if len(visible_items) > hist_first_idx:
        panel_ranges.append((cr, hist_h, hist_first_idx, len(visible_items) - 1, "HISTORY"))

    # -- STATS panel (bottom-left, below history) --
    cr_stats = cr + hist_h
    if stats_lh >= 4:
        range_label, _ = STATS_RANGES[state.get("stats_range", 2)]
        range_tabs = "  ".join(
            f"[{r[0]}]" if i == state.get("stats_range", 2) else r[0]
            for i, r in enumerate(STATS_RANGES)
        )
        stats_first_idx = len(visible_items)
        stats_hl_active = state.get("focus") == "left" and state.get("selected", -1) < 0
        draw_box(stdscr, cr_stats, 0, stats_lh, lw, title=f"STATS  {range_tabs}",
                 border_attr=CYAN if stats_hl_active else 0)
        sr = cr_stats + 1
        max_sr = cr_stats + stats_lh - 1

        def _bar(val: int, max_val: int, bw: int = 8) -> str:
            filled = int(val / max_val * bw) if max_val > 0 else 0
            return "\u2588" * filled + "\u2591" * (bw - filled)

        # Team metrics
        if teams and sr < max_sr - 2:
            for team in teams:
                if sr >= max_sr - 1:
                    break
                tl = team["tasks"]
                t_done = sum(1 for t in tl if t.get("status") == "completed")
                t_active = sum(1 for t in tl if t.get("status") == "in_progress")
                t_pending = sum(1 for t in tl if t.get("status") == "pending")
                t_total = len(tl)
                L(sr, 2, f"TEAMS  {team['name']}", CYAN)
                sr += 1
                if t_total > 0:
                    bar = _progress_bar(t_done, t_active, t_total, 10)
                    summary = f"{bar} {t_total} task{'s' if t_total != 1 else ''}  {t_done} done  {t_active} active  {t_pending} pending"
                    L(sr, 2, summary, DIM)
                    sr += 1
                sr += 1

        # Agent rankings
        if top_agents and sr < max_sr - 1:
            L(sr, 2, f"AGENTS  {range_label}", CYAN)
            sr += 1
            max_a = top_agents[0]["cnt"]
            tag_w = max((len(dir_tag(e.get("cwd", ""))) for e in top_agents), default=0)
            type_w = max((len(e["agent_type"] or "?") for e in top_agents), default=0)
            for entry in top_agents:
                if sr >= max_sr:
                    break
                tag = dir_tag(entry.get("cwd", ""))
                atype = entry["agent_type"] or "?"
                cnt = entry["cnt"]
                bar = _bar(cnt, max_a)
                col1 = tag.ljust(tag_w)
                col2 = atype.ljust(type_w)
                stat_item = {"agent_id": atype, "agent_type": atype, "session_id": "",
                             "started_at": "", "cwd": entry.get("cwd", ""), "is_stat": True,
                             "stat_kind": "agent", "stat_count": cnt, "stat_label": f"{tag} {atype}"}
                vidx = len(visible_items)
                visible_items.append(stat_item)
                is_sel = (vidx == state.get("selected", -1))
                if is_sel:
                    try:
                        stdscr.addnstr(sr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                    except curses.error:
                        pass
                    L(sr, 2, f"{col1}  {col2}  {bar} {cnt}", SEL)
                else:
                    L(sr, 2, f"{col1}  {col2}  {bar} {cnt}", DIM)
                sr += 1
            sr += 1

        # Tool rankings
        if top_tools and sr < max_sr - 1:
            L(sr, 2, f"TOOLS   {range_label}", CYAN)
            sr += 1
            max_t = top_tools[0]["cnt"]
            ttag_w = max((len(dir_tag(e.get("cwd", ""))) for e in top_tools), default=0)
            tname_w = max((len(e["tool_name"] or "?") for e in top_tools), default=0)
            for entry in top_tools:
                if sr >= max_sr:
                    break
                tag = dir_tag(entry.get("cwd", ""))
                tname = entry["tool_name"] or "?"
                cnt = entry["cnt"]
                bar = _bar(cnt, max_t)
                col1 = tag.ljust(ttag_w)
                col2 = tname.ljust(tname_w)
                stat_item = {"agent_id": tname, "agent_type": tname, "session_id": "",
                             "started_at": "", "cwd": entry.get("cwd", ""), "is_stat": True,
                             "stat_kind": "tool", "stat_count": cnt, "stat_label": f"{tag} {tname}"}
                vidx = len(visible_items)
                visible_items.append(stat_item)
                is_sel = (vidx == state.get("selected", -1))
                if is_sel:
                    try:
                        stdscr.addnstr(sr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                    except curses.error:
                        pass
                    L(sr, 2, f"{col1}  {col2}  {bar} {cnt}", SEL)
                else:
                    L(sr, 2, f"{col1}  {col2}  {bar} {cnt}", DIM)
                sr += 1

        # Error rankings
        if error_stats and sr < max_sr - 1:
            sr += 1  # blank line before section
            L(sr, 2, f"ERRORS  {range_label}", RED)
            sr += 1
            max_e = error_stats[0]["cnt"]
            etag_w = max((len(dir_tag(e.get("cwd", ""))) for e in error_stats), default=0)
            ename_w = max((len(e["tool_name"] or "?") for e in error_stats), default=0)
            for entry in error_stats:
                if sr >= max_sr:
                    break
                tag = dir_tag(entry.get("cwd", ""))
                tname = entry["tool_name"] or "?"
                cnt = entry["cnt"]
                bar = _bar(cnt, max_e)
                col1 = tag.ljust(etag_w)
                col2 = tname.ljust(ename_w)
                stat_item = {"agent_id": tname, "agent_type": tname, "session_id": "",
                             "started_at": "", "cwd": entry.get("cwd", ""), "is_stat": True,
                             "stat_kind": "error", "stat_count": cnt, "stat_label": f"{tag} {tname}"}
                vidx = len(visible_items)
                visible_items.append(stat_item)
                is_sel = (vidx == state.get("selected", -1))
                if is_sel:
                    try:
                        stdscr.addnstr(sr, 1, " " * (lw - 2), lw - 2, SEL_DIM)
                    except curses.error:
                        pass
                    L(sr, 2, f"{col1}  {col2}  {bar} {cnt}", SEL_RED)
                else:
                    L(sr, 2, f"{col1}  {col2}  {bar} {cnt}", RED)
                sr += 1

        if len(visible_items) > stats_first_idx:
            stats_title = f"STATS  {range_tabs}"
            panel_ranges.append((cr_stats, stats_lh, stats_first_idx, len(visible_items) - 1, stats_title))

    # Clamp selection to visible items and recompute sel_agent
    state["visible_items"] = visible_items
    if visible_items:
        state["selected"] = max(-1, min(state.get("selected", -1), len(visible_items) - 1))
    else:
        state["selected"] = -1
    sel_idx = state.get("selected", -1)
    sel_agent = visible_items[sel_idx] if 0 <= sel_idx < len(visible_items) else None

    # Highlight the left panel that contains the selected item
    if state.get("focus") == "left" and sel_idx >= 0:
        for py, ph, fi, li, ptitle in panel_ranges:
            if fi <= sel_idx <= li:
                draw_box(stdscr, py, 0, ph, lw, title=ptitle, border_attr=CYAN)
                break

    # -- Right panel (single panel: TREE or TIMELINE, toggled by Tab) --
    if split and rw > 10:
        total_rh = h - content_top - 1
        focused = state.get("focus") == "right"
        viz_mode = VIZ_MODES[state.get("viz_mode", 0) % len(VIZ_MODES)] if state.get("viz_mode", 0) < len(VIZ_MODES) else "life"

        # Build title with tab selector
        tabs = "  ".join(f"[{VIZ_LABELS[m]}]" if m == viz_mode else VIZ_LABELS[m] for m in VIZ_MODES)
        if state.get("game_of_life"):
            tabs += "  LIFE"
        title_prefix = "\u25b6 " if focused else ""
        draw_box(stdscr, content_top, rx, total_rh, rw,
                 title=f"{title_prefix}{tabs}",
                 border_attr=CYAN if focused else 0)

        panel_y = content_top + 1
        panel_h = total_rh - 2

        if viz_mode == "tree":
            # Merged: show DETAIL header + tree for selected item
            if sel_agent:
                pr = panel_y
                rw_abs = rx + rw - 1
                # Header
                sid_short = sel_agent["agent_id"][:7]
                dur = fmt_dur(sel_agent.get("started_at", ""))
                tag = dir_tag(sel_agent.get("cwd", ""))
                if sel_agent.get("is_session"):
                    header = f"{sid_short} \u00b7 {tag} \u00b7 {dur}" if tag else f"{sid_short} \u00b7 {dur}"
                    safe_add(stdscr, pr, rx + 2, header[:rw - 4], rw_abs, GREEN | curses.A_BOLD)
                elif sel_agent.get("is_teammate"):
                    tname = sel_agent.get("teammate_name", "")
                    header = f"{sid_short} \u00b7 {tname} \u00b7 {dur}"
                    safe_add(stdscr, pr, rx + 2, header[:rw - 4], rw_abs, CYAN | curses.A_BOLD)
                elif sel_agent.get("is_stat"):
                    safe_add(stdscr, pr, rx + 2, sel_agent.get("stat_label", "")[:rw - 4], rw_abs, CYAN | curses.A_BOLD)
                else:
                    atype = sel_agent.get("agent_type") or "agent"
                    header = f"{sid_short} \u00b7 {tag} {atype} \u00b7 {dur}" if tag else f"{sid_short} \u00b7 {atype} \u00b7 {dur}"
                    safe_add(stdscr, pr, rx + 2, header[:rw - 4], rw_abs, MAGENTA | curses.A_BOLD)
                pr += 1
                safe_add(stdscr, pr, rx + 2, SYMBOLS["h"] * (rw - 4), rw_abs, DIM)
                pr += 1
                # Tree below header
                _draw_viz_tree(stdscr, pr, rx, panel_y + panel_h - pr, rw, cache, state)
            else:
                _draw_viz_tree(stdscr, panel_y, rx, panel_h, rw, cache, state)

        elif viz_mode == "gantt":
            _draw_viz_gantt(stdscr, panel_y, rx, panel_h, rw, cache, state)

        elif state.get("game_of_life") and state.get("viz_mode", 0) >= len(VIZ_MODES):
            # Game of Life
            life_sid = None
            if sel_agent and sel_agent.get("is_session"):
                life_sid = sel_agent["session_id"]
            if not life_sid and active_all:
                life_sid = active_all[0]["session_id"]
            if not life_sid:
                life_sid = "idle"
            char_w = rw - 4
            char_h = panel_h
            grid_rows = char_h * 4
            grid_cols = char_w * 2
            life_grids = state.setdefault("life_grids", {})
            if life_sid not in life_grids:
                sess_info = session_lookup.get(life_sid, {})
                seed_str = (sess_info.get("prompt", "") or "") + life_sid
                random.seed(hash(seed_str))
                life_grids[life_sid] = {"grid": life_init(grid_rows, grid_cols, 0.25),
                                        "size": (grid_rows, grid_cols), "gen": 0}
                random.seed()
            elif life_grids[life_sid]["size"] != (grid_rows, grid_cols):
                old_grid = life_grids[life_sid]["grid"]
                old_r, old_c = life_grids[life_sid]["size"]
                new_grid = [[False] * grid_cols for _ in range(grid_rows)]
                for r in range(min(old_r, grid_rows)):
                    for c in range(min(old_c, grid_cols)):
                        new_grid[r][c] = old_grid[r][c]
                life_grids[life_sid]["grid"] = new_grid
                life_grids[life_sid]["size"] = (grid_rows, grid_cols)
            lg = life_grids[life_sid]
            for _ in range(5):
                lg["grid"] = life_step(lg["grid"], grid_rows, grid_cols)
                lg["gen"] += 1
            alive = sum(sum(row) for row in lg["grid"])
            if alive < 5:
                sess_info = session_lookup.get(life_sid, {})
                seed_str = (sess_info.get("prompt", "") or "") + life_sid + str(lg["gen"])
                random.seed(hash(seed_str))
                lg["grid"] = life_init(grid_rows, grid_cols, 0.25)
                random.seed()
            _life_colors = [DIM, DIM, CYAN, CYAN, GREEN, GREEN, YELLOW, YELLOW, YELLOW]
            lines = life_render(lg["grid"], grid_rows, grid_cols, char_w, char_h)
            lr = panel_y
            for row in lines:
                if lr >= panel_y + panel_h:
                    break
                cx = rx + 2
                for bch, density in row:
                    if cx >= rx + rw - 1:
                        break
                    safe_add(stdscr, lr, cx, bch, rx + rw - 1, _life_colors[min(density, 8)])
                    cx += 1
                lr += 1

    # -- Footer (full width) --
    status = state.get("status_msg", "")
    if status and time.time() < state.get("status_until", 0):
        safe_add(stdscr, h - 1, 0, f" {status}", w, YELLOW)
    elif visible_items:
        if state.get("focus") == "right":
            safe_add(stdscr, h - 1, 0, " j/k=scroll  h=back  tab=viz  enter=open  q=quit", w, DIM)
        elif state.get("selected", -1) >= 0:
            safe_add(stdscr, h - 1, 0, " j/k=select  l/enter=detail  h/l=stats  tab=viz  esc=deselect  q=quit", w, DIM)
        else:
            safe_add(stdscr, h - 1, 0, " j/k=select  h/l=stats range  tab=viz  q=quit", w, DIM)
    else:
        safe_add(stdscr, h - 1, 0, " tab=viz  q=quit", w, DIM)
    stdscr.refresh()


RENDER_MS = 200     # redraw interval (5 FPS — smooth enough, less CPU)
DATA_FRAMES = 10    # refresh DB every N frames (~2s at 200ms)


def main(stdscr, game_of_life=False):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(RENDER_MS)
    stdscr.keypad(True)

    init_colors()

    state: dict = {"selected": 0, "visible_items": [], "status_msg": "", "status_until": 0.0,
                   "stats_range": 2, "game_of_life": game_of_life, "focus": "left", "detail_scroll": 0,
                   "viz_mode": 0, "tree_filter": 0}
    cache: dict = {}
    refresh_data(cache, state["stats_range"])
    frame = 0
    while True:
        if frame % DATA_FRAMES == 0:
            refresh_data(cache, state["stats_range"])
        draw(stdscr, frame, state, cache)
        frame += 1
        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            break
        elif ch == 9:  # Tab — cycle viz mode forward, auto-focus right panel
            n_modes = len(VIZ_MODES) + (1 if state.get("game_of_life") else 0)
            state["viz_mode"] = (state["viz_mode"] + 1) % n_modes
            state["detail_scroll"] = 0; state["tree_cursor"] = 0
            state["_expanded_tool"] = -1
            state["focus"] = "right"
        elif ch == 353:  # Shift-Tab — cycle viz mode backward, auto-focus right panel
            n_modes = len(VIZ_MODES) + (1 if state.get("game_of_life") else 0)
            state["viz_mode"] = (state["viz_mode"] - 1) % n_modes
            state["detail_scroll"] = 0; state["tree_cursor"] = 0
            state["_expanded_tool"] = -1
            state["focus"] = "right"
        elif ch == 27:  # Esc — peek ahead to discard escape sequences (arrow keys etc.)
            stdscr.nodelay(True)
            next_ch = stdscr.getch()
            if next_ch == -1:
                # Pure Esc press (no sequence following)
                if state["focus"] == "right":
                    state["focus"] = "left"
                    state["detail_scroll"] = 0; state["tree_cursor"] = 0
                    state["_expanded_tool"] = -1
                else:
                    state["selected"] = -1
            # else: was an escape sequence — ignore (arrow keys handled by KEY_UP etc.)
            stdscr.timeout(RENDER_MS)
        elif ch in (ord("j"), curses.KEY_DOWN):
            if state["focus"] == "right":
                tc = state.get("tree_cursor", 0)
                tl = state.get("_tree_len", 0)
                state["tree_cursor"] = min(tc + 1, max(0, tl - 1))
            else:
                agents = state["visible_items"]
                if agents:
                    state["selected"] = min(state["selected"] + 1, len(agents) - 1) if state["selected"] >= 0 else 0
        elif ch in (ord("k"), curses.KEY_UP):
            if state["focus"] == "right":
                state["tree_cursor"] = max(0, state.get("tree_cursor", 0) - 1)
            elif state["selected"] > 0:
                state["selected"] -= 1
        elif ch in (ord("l"), curses.KEY_RIGHT):
            # Graph mode: move to next sibling at same layer
            viz_m = VIZ_MODES[state.get("viz_mode", 0) % len(VIZ_MODES)] if state.get("viz_mode", 0) < len(VIZ_MODES) else ""
            gn = state.get("graph_nodes", [])
            if state["focus"] == "right" and viz_m == "graph" and gn:
                gh = state.get("graph_hover", 0)
                cur_layer = gn[gh]["layer"] if gh < len(gn) else -1
                for i in range(gh + 1, len(gn)):
                    if gn[i]["layer"] == cur_layer:
                        state["graph_hover"] = i
                        break
                    elif gn[i]["layer"] != cur_layer:
                        break  # passed this layer
            else:
                sel = state["selected"]
                items = state["visible_items"]
                sel_is_stat = 0 <= sel < len(items) and items[sel].get("is_stat")
                if state["focus"] == "left" and sel >= 0 and not sel_is_stat:
                    state["focus"] = "right"
                    state["detail_scroll"] = 0; state["tree_cursor"] = 0
                    state["_expanded_tool"] = -1
                    state["graph_hover"] = 0
                else:
                    old = state["stats_range"]
                    state["stats_range"] = min(old + 1, len(STATS_RANGES) - 1)
                    if state["stats_range"] != old:
                        refresh_data(cache, state["stats_range"])
        elif ch in (ord("h"), curses.KEY_LEFT):
            viz_m = VIZ_MODES[state.get("viz_mode", 0) % len(VIZ_MODES)] if state.get("viz_mode", 0) < len(VIZ_MODES) else ""
            gn = state.get("graph_nodes", [])
            if state["focus"] == "right" and viz_m == "graph" and gn:
                gh = state.get("graph_hover", 0)
                cur_layer = gn[gh]["layer"] if gh < len(gn) else -1
                for i in range(gh - 1, -1, -1):
                    if gn[i]["layer"] == cur_layer:
                        state["graph_hover"] = i
                        break
                    elif gn[i]["layer"] != cur_layer:
                        break  # passed this layer
            elif state["focus"] == "right":
                state["focus"] = "left"
                state["detail_scroll"] = 0; state["tree_cursor"] = 0
                state["_expanded_tool"] = -1
            else:
                old = state["stats_range"]
                state["stats_range"] = max(old - 1, 0)
                if state["stats_range"] != old:
                    refresh_data(cache, state["stats_range"])
        elif ch in (32, 10, 13, curses.KEY_ENTER):  # Space or Enter
            if ch in (10, 13, curses.KEY_ENTER) and state["focus"] == "left" and state["selected"] >= 0:
                # Enter from left focuses right panel
                state["focus"] = "right"
                state["detail_scroll"] = 0; state["tree_cursor"] = 0
                state["_expanded_tool"] = -1
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


def self_update():
    """Upgrade via uv."""
    result = subprocess.run(
        ["uv", "tool", "upgrade", "agent-top"],
        capture_output=False,
    )
    sys.exit(result.returncode)


def setup(no_ccnotify=False):
    from pathlib import Path
    import shutil
    import importlib.resources
    import stat

    dest = Path.home() / ".claude" / "ccnotify" / "ccnotify.py"

    if no_ccnotify:
        print("  Skipping ccnotify installation.")
    elif dest.exists():
        print(f"  ccnotify.py already exists at {dest} — skipping (delete it first to reinstall)")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with importlib.resources.path("agent_top", "_ccnotify.py") as src:
            shutil.copy(src, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  ccnotify.py  →  {dest}")

    if not no_ccnotify:
        print()
        print("Add these hooks to ~/.claude/settings.json:")
        print()
        print(f'''\
{{
  "hooks": {{
    "SessionStart":     [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} SessionStart"}}]}}],
    "SessionEnd":       [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} SessionEnd"}}]}}],
    "SubagentStart":    [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} SubagentStart"}}]}}],
    "SubagentStop":     [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} SubagentStop"}}]}}],
    "UserPromptSubmit": [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} UserPromptSubmit"}}]}}],
    "Stop":             [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} Stop"}}]}}],
    "Notification":     [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} Notification"}}]}}],
    "PreToolUse":       [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} PreToolUse"}}]}}],
    "PostToolUse":      [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} PostToolUse"}}]}}],
    "PostToolUseFailure": [{{"matcher": "", "hooks": [{{"type": "command", "command": "{dest} PostToolUseFailure"}}]}}]
  }}
}}''')
    print()
    print("Done. Run: agent-top")


def cli():
    parser = argparse.ArgumentParser(
        prog="agent-top",
        description="Live terminal dashboard for Claude Code sessions & agents.\n"
                    "Tree view: agents nested under sessions, tool feed for agentless sessions.\n"
                    "Run in a separate pane alongside Claude Code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"agent-top v{VERSION}"
    )
    parser.add_argument(
        "--setup", action="store_true", help="install ccnotify hooks and print settings.json config"
    )
    parser.add_argument(
        "--no-ccnotify", action="store_true", help="use --setup without installing ccnotify"
    )
    parser.add_argument(
        "--update", action="store_true", help="self-update from GitHub"
    )
    parser.add_argument(
        "--game-of-life", action="store_true", help="show Conway's Game of Life"
    )
    args = parser.parse_args()

    if args.setup:
        setup(no_ccnotify=getattr(args, "no_ccnotify", False))
        sys.exit(0)

    if args.update:
        self_update()
        sys.exit(0)

    try:
        curses.wrapper(lambda stdscr: main(stdscr, game_of_life=args.game_of_life))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    cli()
