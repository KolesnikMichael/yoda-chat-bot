---
id: TASK-006
epic: EPIC-001
title: "compression apply and size trigger"
status: done
priority: high
size: L
created: 2026-06-09
updated: 2026-06-18
tags:
  - chat-context
---

# TASK-006: compression apply and size trigger

## Description

Implement the full compression apply pipeline: a per-conversation `asyncio.Lock`; snapshot → transformation on the copy (steps 1–10) → graft+merge with `new_arrivals` reconciliation; inline `summary` blocks with `MAX_SUMMARY_COUNT` FIFO eviction into `pending_vectorization`; the `Chat.history` audit entry; and the `user_introduction` strip (step 2) + refresh (step 8) + merge reconciliation reusing the Core helper from TASK-002. The summarisation call is delegated to `SummarizerProvider` (TASK-005); transformation step 5 applies the returned per-user `profile_updates` **deltas** via `MemoryProvider.update_user_profile` (not wholesale profile replacement) **before** the `user_introduction` refresh (step 8). Wire **only the size-trigger** into `compress_conversations`. This is the program's main integration milestone — after it, long chats compress inline without Chroma.

## Master design

- [[chat_context_management#Compression apply]]
- [[chat_context_management#Lock model]]
- [[chat_context_management#Refresh during compression]]
- [[chat_context_management#Profile extraction details]] (step-5 ordering)
- [[chat_context_management#Summarizer envelope]] (`SummarizerProvider` contract)
- [[chat_context_management#Size-trigger — emergency cutoff]]
- [[chat_context_management#Chathistory schema]]
- [[ADR-000-sensitive-data-persistence]] (apply is in-memory; conversation stash is graceful-shutdown-only)

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- Snapshot / transformation on the copy / apply graft+merge (including concurrent ingest during the LLM call)
- `user_introduction` strip (step 2) + refresh (step 8) + merge reconciliation — **reusing the TASK-002 Core helper**, not a new implementation
- Invoking `SummarizerProvider` (TASK-005) for the summarisation call; loading current `UserProfile` snapshots as LLM context only; applying returned `profile_updates` deltas in transformation step 5 via `MemoryProvider.update_user_profile` (TASK-000 merge semantics) **before** the `user_introduction` refresh (step 8)
- Inline `summary` blocks; FIFO eviction → `pending_vectorization` (the outbox accumulates; flush is still a no-op here)
- `Chat.history` compression audit entry
- Size-trigger wiring in `Maintenance.compress_conversations` (using the `CompressionCore` size-window + firing predicate)
- Post-apply invariant tests, incl. a deterministic "messages arrived during the LLM call" test (inject via the fake LLM/ingest)

**Out of scope:**
- timeout-trigger wiring (TASK-007)
- the summariser/profile internals themselves (TASK-005)
- Chroma / `flush_summary_outbox` implementation (TASK-008)
- `recall_conversation` skill (TASK-009)

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on:
  - [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]
  - [[TASK-002-user-introduction-on-ingest/task|TASK-002]]
  - [[TASK-003-compression-window-algorithms-core/task|TASK-003]]
  - [[TASK-004-maintenance-integration-shell/task|TASK-004]]
  - [[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]
- Blocks:
  - [[TASK-007-timeout-trigger-wiring/task|TASK-007]]
  - [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]

## Notes

The largest stage (L), even after extracting the summariser into TASK-005. Program milestone: user value without vector recall. Do not split the apply itself — the snapshot/transform/graft invariants give no valid intermediate state. Apply commits in-memory only per ADR-000; `pending_vectorization` is checkpointed with the rest of the conversation on graceful shutdown, not on each apply.
