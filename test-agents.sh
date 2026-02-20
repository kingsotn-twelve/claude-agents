#!/usr/bin/env bash
# test-agents.sh — simulate background agents for dashboard testing
# Usage: ./test-agents.sh [count] [min_sleep] [max_sleep]
#   count      number of agents to spin up (default 5)
#   min_sleep  minimum sleep seconds (default 5)
#   max_sleep  maximum sleep seconds (default 20)

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
DB="${CLAUDE_AGENTS_DB:-$HOME/.claude/ccnotify/ccnotify.db}"

COUNT="${1:-5}"
MIN="${2:-5}"
MAX="${3:-20}"

AGENT_TYPES=(Explore Plan Bash Debug Frontend API general-purpose)

SESSION_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
CWD="$DIR"

echo "session  $SESSION_ID"
echo "agents   $COUNT  sleep ${MIN}–${MAX}s"
echo ""

# Create parent session
sqlite3 "$DB" "INSERT INTO prompt (session_id, prompt, cwd) VALUES ('$SESSION_ID', 'test: $COUNT agents', '$CWD');"

# Spin up agents in parallel
for i in $(seq 1 "$COUNT"); do
    AGENT_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
    AGENT_TYPE="${AGENT_TYPES[$((RANDOM % ${#AGENT_TYPES[@]}))]}"
    SLEEP=$((RANDOM % (MAX - MIN + 1) + MIN))

    sqlite3 "$DB" "INSERT INTO agent (agent_id, agent_type, session_id, cwd, started_at) VALUES ('$AGENT_ID', '$AGENT_TYPE', '$SESSION_ID', '$CWD', CURRENT_TIMESTAMP);"
    printf "  [%d] %-16s %ds  %s\n" "$i" "$AGENT_TYPE" "$SLEEP" "$AGENT_ID"

    (
        sleep "$SLEEP"
        sqlite3 "$DB" "UPDATE agent SET stopped_at = CURRENT_TIMESTAMP WHERE agent_id = '$AGENT_ID';"
        printf "  [%d] %-16s done\n" "$i" "$AGENT_TYPE"
    ) &
done

wait
sqlite3 "$DB" "UPDATE prompt SET stoped_at = CURRENT_TIMESTAMP WHERE session_id = '$SESSION_ID';"
echo ""
echo "done."
