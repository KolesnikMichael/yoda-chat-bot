---
id: TASK-000
epic: EPIC-001
title: "compression prerequisites"
status: done
priority: medium
size: S
created: 2026-06-09
updated: 2026-06-12
tags:
  - chat-context
---

# TASK-000: compression prerequisites

## Description

Prepare two independent changes from the master design that compression apply depends on (but which do not block the schema work): include skill names in the content of `task_result` messages, and extend `UserProfile` with a `skill_preferences` field plus delta semantics in `update_user_profile`. Both are small, additive, and self-contained schema/content widenings.

## Master design

- [[chat_context_management#Prerequisites]]

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- `Tools used: …` in `task_result` content produced by `Mind._handle_agent_result` (reminder- and failure-style `task_result` records keep their current content; the mechanical extractor treats their `skills` set as empty)
- `UserProfile.skill_preferences` field + extension of `MemoryProvider.update_user_profile` with the delta keys `interests_to_add`, `facts_to_add`, `skill_preferences_to_add` (append-with-dedup; replace-style keys stay available for the agent tool)
- `update_profile` agent tool: add `skill_preferences` to `ALLOWED_FIELDS`

**Out of scope:**
- `Message.kind`, migration, compression, Maintenance, vector store
- Consuming the delta keys (done in TASK-005) and the mechanical `skills`/`participants` computation (done in TASK-005)

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design (source of truth)
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on: —
- Blocks:
  - [[TASK-002-user-introduction-on-ingest/task|TASK-002]] (needs `UserProfile.skill_preferences` for the `user_introduction` snapshot)
  - [[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]] (needs the delta keys, the field, and skill names in `task_result`)

## Notes

TASK-000 and TASK-001 can be done in parallel. Harness artifacts (`requirements`, `design`, `plan`) are filled by the skills, not by hand.
