# Agent Biographies — Design Document

**Date**: 2026-02-21
**Status**: Approved

## Vision

When you select an agent type in the STATS panel, the DETAIL panel shows its biography — a track record computed from existing DB data. One summary line + recent runs with success/fail indicators.

## What You See

```
╭── ▶ explore ─────────────────────────────╮
│                                          │
│  47 runs · 89% success · avg 2m12s       │
│                                          │
│  RECENT                                  │
│  ● 14:23  2m  [claude-agents]  ✓         │
│  ● 13:01  8m  [api-server]    ✗          │
│  ● 12:44  1m  [claude-agents]  ✓         │
│  ○ 11:30  3m  [tl-product]    ✓          │
│                                          │
╰──────────────────────────────────────────╯
```

## Data Model

Query-time aggregation from existing tables. No new storage.

- **Total runs**: `COUNT(*)` from `agent` where `agent_type = ?`
- **Success rate**: agents with `stopped_at IS NOT NULL` and duration > 5s and < 10min = success. Others = failure.
- **Avg duration**: `AVG(stopped_at - started_at)` for completed agents
- **Recent runs**: last 10 completed agents of this type, with timestamp, duration, project (cwd), and success/fail indicator

## Failure Heuristic

An agent run is considered "failed" if:
- Duration < 5 seconds (crashed immediately)
- Duration > 10 minutes (likely stuck/timed out)
- Was orphaned (parent session died)

This is a rough heuristic. Can refine later with actual exit code tracking.

## Implementation

Modify `_draw_detail()` in the stats drill-down section to show the biography view instead of the current raw recent-runs list. Add a new query function `query_agent_biography()` that returns summary stats + recent runs.
