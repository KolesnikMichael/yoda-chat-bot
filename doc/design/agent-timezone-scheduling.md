---
title: "agent timezone scheduling"
updated: 2026-07-22
tags:
  - agent
  - timezone
  - scheduling
---

# Agent timezone scheduling

Durable contract for IANA timezone identity on absolute and recurring schedules.
Historical source: TASK-017 (EPIC-002 Decision 5).

Related: [[design/agent-two-phase-protocol|two-phase protocol]],
`skills/specs/schedule_message.md`, `skills/specs/search_web.md` (deferred
scheduling), `ScheduleCore` in `yoda/mind/agent/core/schedule_core.py`.

## Principle

Persist and schedule with an **IANA timezone name** accepted by `ZoneInfo`.
Never derive identity solely from a UTC offset (`+03:00`, `UTC+03:00`, …).
Explicit `UTC` remains a valid IANA name.

Timezone discovery stays in the **already-selected** skill workflow; validity
stays in deterministic scheduling code. No geocoding Provider in this contract.

## Resolution precedence (absolute / recurring)

For local-time schedules, execution evaluates in order:

1. Valid IANA timezone **explicitly** supplied on the schedule call  
2. Valid profile timezone (`ZoneInfo`)  
3. Unambiguous named location in task or profile → infer IANA, then persist  
4. One `ask_user` for city/region or IANA name  

Invalid, missing, or offset-only candidates are **unresolved** — never coerced
to UTC for local-time registration.

**Relative delays** (`delay_minutes`) bypass this policy: no timezone
clarification; display/metadata may use first valid explicit or profile value,
else `UTC`.

## Self-contained scheduling calls

Every absolute/cron tool request must carry an **explicit** valid `timezone`
argument. Execution copies a reused or inferred name into the call; scheduling
adapters must not silently fall back to `profile_timezone` metadata or UTC for
local-time modes.

When inference produces a timezone:

- Pass it to `update_profile` (timezone + location) **and** to the schedule call  
- Batching/parallel dispatch is allowed because neither call depends on the other  
- Scheduling never rereads the just-written profile to learn identity  

Tool boundary: trim surrounding whitespace, validate with `ZoneInfo`, pass and
persist that normalized name.

## Timing modes (tool schemas)

| Mode | Required | Timezone |
|------|----------|----------|
| Relative | `delay_minutes` | Optional (display/metadata only) |
| Absolute | year/month/day/hour/minute | Explicit valid IANA required |
| Recurring | `cron` | Explicit valid IANA required |

Exactly one timing mode per call.

## ScheduleCore

```text
validate_timezone_name(timezone) -> normalized name | None
relative_timezone_name(explicit, profile) -> display tz (never authorizes local schedule)
```

Adapters reject missing/invalid/offset local identity **before** `SchedulerApi`
or metadata writes.

## DST

Tests cover unambiguous wall times around spring/autumn transitions with real
`ZoneInfo` / `CronTrigger`. Fold/gap (nonexistent or duplicated local hour)
policy is out of scope.

## Code map

| Concern | Location |
|---------|----------|
| Workflow policy | `skills/specs/schedule_message.md`, `search_web.md` |
| Validation / conversion | `yoda/mind/agent/core/schedule_core.py` |
| Side effects | `schedule_message_tool.py`, `schedule_task_tool.py` |

## Historical

- [[backlog/archive/TASK-017-iana-timezone-execution-guidance/design|TASK-017 design]]
