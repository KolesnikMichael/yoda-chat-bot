---
id: TASK-003
epic: EPIC-001
title: "compression window algorithms core"
status: todo
priority: medium
size: M
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-003: compression window algorithms core

## Description

Implement `CompressionCore` — pure, sync logic for compression-window selection and trigger firing, with no LLM, lock, or I/O: visibility/activity helpers, the universal boundary-alignment rule, the size-trigger window (halve + align), the timeout-trigger window (gap walk + `no gap → no-op`), `GAP_THRESHOLD` derivation from settings, and the **trigger firing predicates** themselves. Cover with unit tests on synthetic `Message` lists carrying `kind`.

## Master design

- [[chat_context_management#Compression triggers]]
- [[chat_context_management#Boundary alignment by kind (universal rule)]]
- [[chat_context_management#Window selection algorithm]]
- [[chat_context_management#Size-trigger — emergency cutoff]]

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- `CompressionCore` (IODA Core): visibility, boundary alignment, size window, timeout window + no-op when no gap
- **Firing predicates as pure `CompressionCore` static methods** so they live in a Core, never as business logic inside the `Maintenance` Integration: size-trigger entry (`visible_messages > SIZE_TRIGGER_THRESHOLD`), timeout-trigger entry guard (`visible_messages > 2 * MIN_CHUNK_LENGTH`), the quiet-for-N-runs check (`now - last_visible_at >= N * tick`), and the `last_visible_at > last_compressed_at` "changed since last compression" check
- `GAP_THRESHOLD` derivation from `ChatCompressionSettings`
- Unit tests on deterministic fixtures

**Out of scope:**
- LLM / summarizer
- snapshot, lock, apply, graft+merge
- `user_introduction` strip/refresh
- Maintenance wiring, Redis, Chroma

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on: [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]
- Blocks:
  - [[TASK-004-maintenance-integration-shell/task|TASK-004]] (the dry-run stub calls these firing predicates to log real candidates)
  - [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]
  - [[TASK-007-timeout-trigger-wiring/task|TASK-007]]

## Notes

Can run in parallel with TASK-002 after TASK-001. The hardest algorithmic part, fully isolated from async/LLM.
