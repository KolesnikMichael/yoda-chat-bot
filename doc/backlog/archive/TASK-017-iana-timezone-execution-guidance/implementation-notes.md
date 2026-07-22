---
id: TASK-017
doc: implementation-notes
updated: 2026-07-20
---

# TASK-017 implementation notes

## Manual AC smoke (plan 6.2)

Skipped: Redis / live scheduler not available in this implement session.
FR-1…FR-4 acceptance is covered by the automated suite (Core DST, tool-boundary
rejection before side effects, catalog workflow markers, fixed-decision agent
paths for both `schedule_message` and deferred `search_web`).

## Call-site rename during 1.1

`effective_timezone_name` was renamed to `relative_timezone_name`; the two tool
call sites were updated in the same step so the suite stayed green before Stage 2
tightened absolute/cron validation. No design divergence.

## Review fix: incomplete absolute fields

The first review found that partial absolute date fields could accompany a valid
relative or cron mode and be silently ignored. Both scheduling tools now reject
any partial absolute field set before timing-mode selection. Future plans should
state explicitly that the five absolute fields are atomic even when another mode
is otherwise complete. No design or ADR update is needed.
