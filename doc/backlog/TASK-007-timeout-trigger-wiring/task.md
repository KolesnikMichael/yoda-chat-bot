---
id: TASK-007
epic: EPIC-001
title: "timeout trigger wiring"
status: todo
priority: medium
size: S
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-007: timeout trigger wiring

## Description

Wire the timeout-trigger into the existing `compress_conversations` and the apply pipeline from TASK-006. Use the `CompressionCore` timeout firing predicates (quiet-for-N-runs + `last_visible_at > last_compressed_at`) and timeout window selection from TASK-003. Verify the interaction between triggers (variant C: parallel summary blocks, no re-summarisation). Test scenarios: quiet period + gap → compression; continuous activity without a gap → no-op; size-trigger already compressed → timeout adds `summary_v2` next to `summary_v1`.

## Master design

- [[chat_context_management#Timeout-trigger — clean-chunk compression]]
- [[chat_context_management#Interaction between triggers]]

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- Wire the timeout-trigger into `Maintenance.compress_conversations` via the `CompressionCore` firing predicates (no business logic in the Integration)
- Use the `CompressionCore` timeout window selection from TASK-003
- Tests for the two-trigger interaction and variant C

**Out of scope:**
- changes to the apply algorithm (snapshot/transform/merge)
- Chroma, recall skill
- new schema fields

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on:
  - [[TASK-003-compression-window-algorithms-core/task|TASK-003]]
  - [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]
- Blocks: —

## Notes

A small wiring stage once TASK-006 is done. The apply pipeline is reused without changes.
