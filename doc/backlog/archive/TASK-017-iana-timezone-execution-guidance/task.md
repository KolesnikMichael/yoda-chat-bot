---
id: TASK-017
epic: EPIC-002
title: "IANA timezone execution guidance"
status: done
priority: medium
size: S
created: 2026-07-20
updated: 2026-07-21
tags:
  - agent
  - scheduling
  - timezone
  - prompts
---

# TASK-017: IANA timezone execution guidance

## Description

Make scheduling use IANA timezone identity by guiding execution to reuse a valid profile timezone, infer and persist one from an unambiguous named location, and ask directly only when ambiguity remains. Protect the existing `ZoneInfo` and scheduler behavior with timezone and DST-transition tests rather than deriving identity from a current clock or UTC offset.

## Epic

Part of [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Decision 5: Use IANA timezone identity]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Schedule message skill prompt|Schedule message skill prompt]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Search web skill prompt|Search web skill prompt]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Execution context template|Execution context template]]

## Scope boundary

**In scope:**
- Add prompt-first execution guidance for reusing, inferring, clarifying, and persisting IANA timezone names.
- Clarify only ambiguous location input and reject UTC-offset-only timezone identity.
- Add deterministic timezone and DST-transition coverage around existing `ZoneInfo` and scheduling behavior.

**Out of scope:**
- A new location-to-timezone resolver or geocoding Provider.
- General preference precedence, source constraints, outcome delivery, or scheduler replacement.

## Related documents

- [[backlog/archive/TASK-017-iana-timezone-execution-guidance/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/archive/TASK-017-iana-timezone-execution-guidance/design|design]] — architectural solution
- [[backlog/archive/TASK-017-iana-timezone-execution-guidance/plan|plan]] — implementation plan
- [[backlog/archive/TASK-017-iana-timezone-execution-guidance/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[backlog/archive/TASK-015-phase-protocol-and-agent-integration/task|TASK-015]]
- Blocks: [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/task|TASK-018]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
