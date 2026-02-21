#!/usr/bin/env bash
# test-teams.sh — simulate an agent team for dashboard testing (no real Claude sessions)
# Usage: ./test-teams.sh [duration]
#   duration  how many seconds to stay "active" (default 20)

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
DB="${CLAUDE_AGENTS_DB:-$HOME/.claude/ccnotify/ccnotify.db}"
DURATION="${1:-20}"

TEAM_NAME="test-team"
TEAMS_DIR="$HOME/.claude/teams/$TEAM_NAME"
TASKS_DIR="$HOME/.claude/tasks/$TEAM_NAME"

# Generate fake session IDs for each teammate
SESSION_RESEARCHER="$(uuidgen | tr '[:upper:]' '[:lower:]')"
SESSION_IMPLEMENTER="$(uuidgen | tr '[:upper:]' '[:lower:]')"
SESSION_REVIEWER="$(uuidgen | tr '[:upper:]' '[:lower:]')"

echo "team     $TEAM_NAME"
echo "members  researcher implementer reviewer"
echo "duration ${DURATION}s"
echo ""

cleanup() {
    echo "cleaning up..."
    # Mark teammate sessions as stopped
    sqlite3 "$DB" "UPDATE prompt SET stoped_at = CURRENT_TIMESTAMP WHERE session_id IN ('$SESSION_RESEARCHER','$SESSION_IMPLEMENTER','$SESSION_REVIEWER');" 2>/dev/null || true
    # Remove team config + tasks
    rm -rf "$TEAMS_DIR" "$TASKS_DIR"
    echo "done."
}
trap cleanup EXIT

# 1. Create team config
mkdir -p "$TEAMS_DIR"
cat > "$TEAMS_DIR/config.json" <<JSON
{
  "name": "$TEAM_NAME",
  "members": [
    {"agentId": "$SESSION_RESEARCHER",  "name": "researcher",  "agentType": "Explore"},
    {"agentId": "$SESSION_IMPLEMENTER", "name": "implementer", "agentType": "general-purpose"},
    {"agentId": "$SESSION_REVIEWER",    "name": "reviewer",    "agentType": "review"}
  ]
}
JSON

# 2. Create task files
mkdir -p "$TASKS_DIR"
cat > "$TASKS_DIR/1.json" <<JSON
{"id":"1","subject":"Research API design patterns","status":"completed","owner":"researcher"}
JSON
cat > "$TASKS_DIR/2.json" <<JSON
{"id":"2","subject":"Implement auth endpoints","status":"in_progress","activeForm":"Implementing auth endpoints","owner":"implementer"}
JSON
cat > "$TASKS_DIR/3.json" <<JSON
{"id":"3","subject":"Write unit tests","status":"pending","owner":"reviewer","blockedBy":["2"]}
JSON
cat > "$TASKS_DIR/4.json" <<JSON
{"id":"4","subject":"Code review PR #42","status":"in_progress","activeForm":"Reviewing PR #42","owner":"reviewer"}
JSON
cat > "$TASKS_DIR/5.json" <<JSON
{"id":"5","subject":"Update docs","status":"pending","owner":""}
JSON

# 3. Insert fake sessions into DB (simulates active teammate sessions)
sqlite3 "$DB" "INSERT INTO prompt (session_id, prompt, cwd) VALUES
    ('$SESSION_RESEARCHER',  'team:$TEAM_NAME researcher',  '$DIR'),
    ('$SESSION_IMPLEMENTER', 'team:$TEAM_NAME implementer', '$DIR'),
    ('$SESSION_REVIEWER',    'team:$TEAM_NAME reviewer',    '$DIR');" 2>/dev/null || true

echo "sessions inserted, watching dashboard for ${DURATION}s..."
echo "(open claude-agents in another pane to see the TEAMS section)"
echo ""

# 4. Simulate task progress mid-way through
sleep "$((DURATION / 2))"
echo "→ marking task 2 complete, unblocking task 3..."
cat > "$TASKS_DIR/2.json" <<JSON
{"id":"2","subject":"Implement auth endpoints","status":"completed","owner":"implementer"}
JSON
cat > "$TASKS_DIR/3.json" <<JSON
{"id":"3","subject":"Write unit tests","status":"in_progress","activeForm":"Writing unit tests","owner":"implementer"}
JSON
cat > "$TASKS_DIR/4.json" <<JSON
{"id":"4","subject":"Code review PR #42","status":"completed","owner":"reviewer"}
JSON

sleep "$((DURATION / 2))"
# cleanup via trap
