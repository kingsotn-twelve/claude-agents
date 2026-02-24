#!/usr/bin/env bash
# test-agents.sh — simulate background agents for dashboard testing
# Usage: ./test-agents.sh [count] [min_sleep] [max_sleep]
#   count      number of agents to spin up (default 5)
#   min_sleep  minimum sleep seconds (default 5)
#   max_sleep  maximum sleep seconds (default 20)

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
DB="${AGENT_TOP_DB:-$HOME/.claude/ccnotify/ccnotify.db}"

# Enable WAL mode for concurrent writes from parallel subshells
sqlite3 "$DB" "PRAGMA journal_mode=WAL;" >/dev/null 2>&1

COUNT="${1:-5}"
MIN="${2:-5}"
MAX="${3:-20}"

AGENT_TYPES=(Explore Plan Bash Debug Frontend API general-purpose)
TOOL_NAMES=(Read Write Edit Grep Glob Bash WebSearch Task)
TOOL_LABELS=("__init__.py" "config.ts" "schema.py" "class.*Handler" "**/*.tsx" "npm test" '"react hooks"' "search codebase")

SESSION_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
CWD="$DIR"

echo "session  $SESSION_ID"
echo "agents   $COUNT  sleep ${MIN}–${MAX}s"
echo ""

# Create parent session
sqlite3 "$DB" "INSERT INTO prompt (session_id, prompt, cwd) VALUES ('$SESSION_ID', 'test: $COUNT agents', '$CWD');"

# Insert a Task tool_event just before each agent starts (mimics real Claude Code behavior)
# Then spin up agents in parallel, each generating tool events with matching cwd
for i in $(seq 1 "$COUNT"); do
    AGENT_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
    AGENT_TYPE="${AGENT_TYPES[$((RANDOM % ${#AGENT_TYPES[@]}))]}"
    SLEEP=$((RANDOM % (MAX - MIN + 1) + MIN))
    AGENT_CWD="$CWD/.claude/worktrees/agent-$i"

    # Task tool_event (fires just before SubagentStart)
    sqlite3 "$DB" "INSERT INTO tool_event (session_id, tool_name, tool_label, tool_use_id, cwd) VALUES ('$SESSION_ID', 'Task', '$AGENT_TYPE: job $i', '$(uuidgen)', '$CWD');"

    sqlite3 "$DB" "INSERT INTO agent (agent_id, agent_type, session_id, cwd, started_at) VALUES ('$AGENT_ID', '$AGENT_TYPE', '$SESSION_ID', '$AGENT_CWD', CURRENT_TIMESTAMP);"
    printf "  [%d] %-16s %ds  %s\n" "$i" "$AGENT_TYPE" "$SLEEP" "$AGENT_ID"

    (
        # Generate 2-4 tool events per agent with matching cwd
        TOOL_COUNT=$((RANDOM % 3 + 2))
        for j in $(seq 1 "$TOOL_COUNT"); do
            sleep 1
            TNAME="${TOOL_NAMES[$((RANDOM % ${#TOOL_NAMES[@]}))]}"
            TLABEL="${TOOL_LABELS[$((RANDOM % ${#TOOL_LABELS[@]}))]}"
            sqlite3 "$DB" "INSERT INTO tool_event (session_id, tool_name, tool_label, tool_use_id, cwd) VALUES ('$SESSION_ID', '$TNAME', '$TLABEL', '$(uuidgen)', '$AGENT_CWD');"
        done
        sleep "$SLEEP"
        sqlite3 "$DB" "UPDATE agent SET stopped_at = CURRENT_TIMESTAMP WHERE agent_id = '$AGENT_ID';"
        printf "  [%d] %-16s done\n" "$i" "$AGENT_TYPE"
    ) &
done

wait
sqlite3 "$DB" "UPDATE prompt SET stoped_at = CURRENT_TIMESTAMP WHERE session_id = '$SESSION_ID';"
echo ""
echo "done."
