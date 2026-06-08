---
id: TASK-004
title: "maintenance integration shell"
status: todo
priority: medium
size: S
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-004: maintenance integration shell

## Description

Introduce the `Maintenance` Integration with a single periodic tick loop, move `reconcile_active_jobs` / `periodic_job_cleanup` out of `yoda_chat_bot.py`, and expose `run_initial_pass`, `start`, and `stop`. Add a `compress_conversations` stub (dry-run: only evaluate and log trigger candidates via `CompressionCore` predicates) and a `flush_summary_outbox` stub (no-op). Prepare the wiring seam for real compression in TASK-006.

## Master design

- [[chat_context_management#Maintenance integration]]
- [[chat_context_management#Single ticking loop]]

## Program

Part of the Chat Context Management chain — see the program map in [[main#Chat Context Management]].

## Scope boundary

**In scope:**
- `Maintenance` Integration class (IODA Integration — orchestration only, **no business logic**: trigger decisions are delegated to `CompressionCore`)
- Single tick loop (`mind.maintenance.tick_minutes`); add `mind.maintenance` block to `settings.json`
- Move `reconcile_active_jobs` out of the wiring file (`cleanup_job_metadata`, the one-line scheduler callback, stays in the wiring file per master design)
- `compress_conversations` stub: log conversations that pass the `CompressionCore` firing predicates (no apply)
- `flush_summary_outbox` stub (no-op)
- Wiring in `yoda_chat_bot.py`: `run_initial_pass`, `start`, `stop`

**Out of scope:**
- the real compression apply
- Chroma / `EmbeddingProvider` / `VectorProvider`
- the summarizer LLM call

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[main#Chat Context Management]] — program map and position in the chain

## Dependencies

- Depends on:
  - [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]
  - [[TASK-003-compression-window-algorithms-core/task|TASK-003]] (the dry-run stub calls its firing predicates)
- Blocks: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]

## Notes

Can run in parallel with TASK-002 after TASK-001 + TASK-003. `cleanup_job_metadata` stays in the wiring file per master design.
