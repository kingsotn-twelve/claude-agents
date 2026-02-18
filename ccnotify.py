#!/usr/bin/env python3
"""
Claude Code Notify — desktop notifications for Claude Code hooks.
Consolidated handler for Stop, SubagentStart, SubagentStop, Notification, and UserPromptSubmit.
"""

import json
import logging
import os
import random
import sqlite3
import subprocess
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(SCRIPT_DIR, "sounds")

# macOS system sounds — one per event type, simple and not annoying.
SYSTEM_SOUNDS: dict[str, str] = {
    "task_complete": "/System/Library/Sounds/Blow.aiff",
    "subagent_complete": "/System/Library/Sounds/Blow.aiff",
    "waiting_input": "/System/Library/Sounds/Blow.aiff",
    "permission": "/System/Library/Sounds/Blow.aiff",
    "error": "/System/Library/Sounds/Basso.aiff",
}

def _pick_sound(event_key: str) -> str | None:
    """Return the system sound path for this event type."""
    path = SYSTEM_SOUNDS.get(event_key, SYSTEM_SOUNDS["task_complete"])
    return path if os.path.exists(path) else None


def iterm_info() -> dict:
    """Get iTerm2 window/pane info for the session that fired the hook (not the focused one)."""
    info = {"window": "", "window_num": 0, "window_total": 0,
            "pane_num": 0, "pane_total": 0, "pane_name": ""}

    # ITERM_SESSION_ID looks like "w0t0p5:C6684449-..."  — the UUID after ':' is the unique ID
    iterm_session_id = os.environ.get("ITERM_SESSION_ID", "")
    target_id = iterm_session_id.split(":")[-1] if ":" in iterm_session_id else ""
    if not target_id:
        return info

    try:
        result = subprocess.run(
            ["osascript", "-e", f"""
tell application "iTerm2"
  set winList to windows
  set winCount to count of winList
  repeat with wi from 1 to winCount
    set w to item wi of winList
    set winName to name of w
    tell w
      repeat with t in tabs
        set sessList to sessions of t
        set sessCount to count of sessList
        repeat with si from 1 to sessCount
          set s to item si of sessList
          if unique ID of s is "{target_id}" then
            set sessName to name of s
            return winName & "|" & wi & "|" & winCount & "|" & si & "|" & sessCount & "|" & sessName
          end if
        end repeat
      end repeat
    end tell
  end repeat
  return "|0|0|0|0|"
end tell"""],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            raw_win = parts[0] if parts else ""
            info["window"] = raw_win.lstrip("\u2800\u2801\u2802\u2803\u2804\u2808\u2810\u2820\u2840\u2880\u2900 ")
            info["window_num"] = int(parts[1]) if len(parts) > 1 else 0
            info["window_total"] = int(parts[2]) if len(parts) > 2 else 0
            info["pane_num"] = int(parts[3]) if len(parts) > 3 else 0
            info["pane_total"] = int(parts[4]) if len(parts) > 4 else 0
            info["pane_name"] = parts[5].strip() if len(parts) > 5 else ""
    except Exception:
        pass
    return info


def _location_label(iterm: dict) -> str:
    """Build a human-readable location string like 'Win 2/4 · Pane 3/5 · my-pane'."""
    parts = []
    if iterm["window_num"]:
        parts.append(f"Win {iterm['window_num']}/{iterm['window_total']}")
    if iterm["pane_num"]:
        parts.append(f"Pane {iterm['pane_num']}/{iterm['pane_total']}")
    if iterm["pane_name"]:
        # Strip braille spinner prefixes from pane name too
        name = iterm["pane_name"].lstrip("\u2800\u2801\u2802\u2803\u2804\u2808\u2810\u2820\u2840\u2880\u2900 ")
        if name:
            parts.append(name)
    return " · ".join(parts)


def play_sound(sound_key: str) -> None:
    """Play a Clash Royale sound effect, cycling through the list."""
    path = _pick_sound(sound_key)
    if path:
        try:
            subprocess.Popen(
                ["afplay", "-v", "0.7", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logging.info(f"Playing sound: {os.path.basename(path)} for {sound_key}")
        except Exception:
            pass


def send_notification(title: str, subtitle: str, message: str = "",
                      sound_key: str = "task_complete", cwd: str | None = None) -> None:
    """Send macOS notification via terminal-notifier with click-to-focus iTerm."""
    play_sound(sound_key)

    try:
        cmd = [
            "terminal-notifier",
            "-title", title,
            "-subtitle", subtitle,
        ]
        if message:
            cmd.extend(["-message", message])
        # Use Finder as sender so macOS never suppresses the banner
        # (banners are hidden when the sender app is focused — Finder is never focused)
        cmd.extend(["-sender", "com.apple.Finder"])
        # Click notification -> activate iTerm
        cmd.extend(["-activate", "com.googlecode.iterm2"])
        cmd.extend(["-ignoreDnD"])
        if cwd:
            cmd.extend(["-group", f"claude-{os.path.basename(cwd)}"])

        subprocess.run(cmd, check=False, capture_output=True, timeout=5)
        logging.info(f"Notified: {title} | {subtitle} | {message}")
    except FileNotFoundError:
        # Fallback to osascript if terminal-notifier missing
        try:
            safe_title = title.replace('"', '\\"')
            safe_sub = subtitle.replace('"', '\\"')
            script = f'display notification "{safe_sub}" with title "{safe_title}"'
            subprocess.run(["osascript", "-e", script], check=False,
                           capture_output=True, timeout=5)
        except Exception:
            pass
    except Exception as e:
        logging.error(f"Notification error: {e}")


class ClaudePromptTracker:
    def __init__(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(script_dir, "ccnotify.db")
        self.setup_logging()
        self.init_database()

    def setup_logging(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(script_dir, "ccnotify.log")
        handler = TimedRotatingFileHandler(
            log_path, when="midnight", interval=1, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S",
        ))
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    prompt TEXT,
                    cwd TEXT,
                    seq INTEGER,
                    stoped_at DATETIME,
                    lastWaitUserAt DATETIME
                )
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS auto_increment_seq
                AFTER INSERT ON prompt
                FOR EACH ROW
                BEGIN
                    UPDATE prompt SET seq = (
                        SELECT COALESCE(MAX(seq), 0) + 1
                        FROM prompt WHERE session_id = NEW.session_id
                    ) WHERE id = NEW.id;
                END
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL UNIQUE,
                    agent_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    cwd TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    stopped_at DATETIME,
                    transcript_path TEXT
                )
            """)
            conn.commit()

    def handle_subagent_start(self, data: dict) -> None:
        agent_id = data.get("agent_id", "")
        agent_type = data.get("agent_type", "unknown")
        session_id = data.get("session_id", "")
        cwd = data.get("cwd", "")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO agent (agent_id, agent_type, session_id, cwd, started_at, stopped_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)""",
                (agent_id, agent_type, session_id, cwd),
            )
            conn.commit()
        logging.info(f"Agent started: {agent_type} id={agent_id} session={session_id}")

    def handle_subagent_stop(self, data: dict) -> None:
        agent_id = data.get("agent_id", "")
        agent_type = data.get("agent_type", "unknown")
        session_id = data.get("session_id", "")
        transcript_path = data.get("agent_transcript_path", "")
        with sqlite3.connect(self.db_path) as conn:
            # Update if we tracked the start, otherwise insert a completed record
            conn.execute(
                """INSERT INTO agent (agent_id, agent_type, session_id, started_at, stopped_at, transcript_path)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                       stopped_at = CURRENT_TIMESTAMP,
                       transcript_path = excluded.transcript_path""",
                (agent_id, agent_type, session_id, transcript_path),
            )
            conn.commit()
        logging.info(f"Agent stopped: {agent_type} id={agent_id} session={session_id}")

    def handle_user_prompt_submit(self, data: dict) -> None:
        session_id = data.get("session_id")
        prompt = data.get("prompt", "")
        cwd = data.get("cwd", "")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO prompt (session_id, prompt, cwd) VALUES (?, ?, ?)",
                (session_id, prompt, cwd),
            )
            conn.commit()
        logging.info(f"Prompt recorded session={session_id}")

    def handle_stop(self, data: dict, is_subagent: bool = False) -> None:
        session_id = data.get("session_id")
        cwd = data.get("cwd", "")
        iterm = iterm_info()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT id, created_at, cwd FROM prompt
                   WHERE session_id = ? AND stoped_at IS NULL
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id,),
            )
            row = cursor.fetchone()

            if row:
                record_id = row[0]
                conn.execute(
                    "UPDATE prompt SET stoped_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (record_id,),
                )
                conn.commit()
                seq = conn.execute(
                    "SELECT seq FROM prompt WHERE id = ?", (record_id,),
                ).fetchone()
                seq = seq[0] if seq else 1
                duration = self._duration(record_id)
            else:
                seq = "?"
                duration = ""

        if is_subagent:
            prefix = "Agent done"
            sound = "subagent_complete"
        else:
            prefix = "Done"
            sound = "task_complete"

        title = iterm["window"] or os.path.basename(cwd)
        loc = _location_label(iterm)
        subtitle = f"{prefix} #{seq}" + (f" ({duration})" if duration else "")

        send_notification(title, subtitle, loc, sound, cwd)
        logging.info(f"Stop session={session_id} window={iterm['window']!r} win={iterm['window_num']}/{iterm['window_total']} pane={iterm['pane_num']}/{iterm['pane_total']} {prefix} #{seq} {duration}")

    def handle_notification(self, data: dict) -> None:
        session_id = data.get("session_id")
        message = data.get("message", "")
        cwd = data.get("cwd", "")
        iterm = iterm_info()
        msg_lower = message.lower()

        title = iterm["window"] or os.path.basename(cwd)
        loc = _location_label(iterm)

        logging.info(f"Notification session={session_id} window={iterm['window']!r} win={iterm['window_num']}/{iterm['window_total']} pane={iterm['pane_num']}/{iterm['pane_total']} message={message!r}")

        if "waiting for your input" in msg_lower or "waiting for input" in msg_lower:
            # Suppress if Stop already fired for this session's latest prompt.
            # The user already got a "Done" notification — no need to nag again.
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """SELECT stoped_at FROM prompt
                       WHERE session_id = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (session_id,),
                ).fetchone()
                if row and row[0] is not None:
                    logging.info(f"Suppressed 'waiting for input' — Stop already fired for session={session_id}")
                    return

                conn.execute("""
                    UPDATE prompt SET lastWaitUserAt = CURRENT_TIMESTAMP
                    WHERE id = (
                        SELECT id FROM prompt WHERE session_id = ?
                        ORDER BY created_at DESC LIMIT 1
                    )""", (session_id,))
                conn.commit()
            send_notification(title, "Waiting for input", loc, "waiting_input", cwd)
        elif "permission" in msg_lower:
            send_notification(title, "Permission required", loc, "permission", cwd)
        elif "error" in msg_lower or "failed" in msg_lower:
            send_notification(title, "Error", loc, "error", cwd)
        elif "approval" in msg_lower or "choose an option" in msg_lower:
            send_notification(title, "Action required", loc, "waiting_input", cwd)
        else:
            send_notification(title, "Notification", loc, "task_complete", cwd)

    def _duration(self, record_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT created_at, stoped_at FROM prompt WHERE id = ?",
                (record_id,),
            ).fetchone()
        if not row or not row[1]:
            return ""
        try:
            start = datetime.fromisoformat(row[0])
            end = datetime.fromisoformat(row[1])
            secs = int((end - start).total_seconds())
            if secs < 60:
                return f"{secs}s"
            elif secs < 3600:
                m, s = divmod(secs, 60)
                return f"{m}m{s}s" if s else f"{m}m"
            else:
                h, remainder = divmod(secs, 3600)
                m = remainder // 60
                return f"{h}h{m}m" if m else f"{h}h"
        except Exception:
            return ""


def main():
    if len(sys.argv) < 2:
        return

    event = sys.argv[1]
    valid = ["UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "Notification"]
    if event not in valid:
        logging.error(f"Invalid event: {event}")
        sys.exit(1)

    raw = sys.stdin.read().strip()
    if not raw:
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logging.error(f"JSON parse error: {e}")
        sys.exit(1)

    tracker = ClaudePromptTracker()

    if event == "UserPromptSubmit":
        tracker.handle_user_prompt_submit(data)
    elif event == "Stop":
        tracker.handle_stop(data, is_subagent=False)
    elif event == "SubagentStart":
        tracker.handle_subagent_start(data)
    elif event == "SubagentStop":
        tracker.handle_subagent_stop(data)
        tracker.handle_stop(data, is_subagent=True)
    elif event == "Notification":
        tracker.handle_notification(data)


if __name__ == "__main__":
    main()
