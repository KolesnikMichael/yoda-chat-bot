---
id: TASK-008
epic: EPIC-001
title: "summary store and outbox flush"
status: done
priority: medium
size: M
created: 2026-06-09
updated: 2026-07-19
tags:
  - chat-context
---

# TASK-008: summary store and outbox flush

## Description

Implement the externalised summary store: an `EmbeddingProvider`, a `VectorProvider` (Chroma persistent), and `Maintenance.flush_summary_outbox` — draining in-memory `Conversation.pending_vectorization` into Chroma with a deterministic `summary_id` and same-process idempotent retry. Add `outbox_health_threshold` operator warnings. Startup Chroma hygiene removes incomplete records when outbox retry is impossible; complete records are always kept. Wire providers into `yoda_chat_bot.py` and the Maintenance tick. Chroma holds derived narratives only per [[ADR-000-sensitive-data-persistence]].

## Master design

- [[chat_context_management#Summary store]]
- [[chat_context_management#Persistence flow]]
- [[chat_context_management#Crash recovery]]
- [[chat_context_management#Record schema]]
- [[chat_context_management#Security baseline]]
- [[ADR-000-sensitive-data-persistence]]

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- `EmbeddingProvider` (OpenRouter `text-embedding-3-small`) behind an API façade so the HTTP call is mockable in tests
- `VectorProvider` (Chroma per-chat collection `chat_{chat_id}`); decide and document the test strategy (ephemeral in-process Chroma vs a fake) and add `chromadb` + the embeddings client to `requirements.txt`, plus the `data/` persistence directory
- `flush_summary_outbox`: embed batch → persist to Chroma → remove flushed entries from in-memory `pending_vectorization` on success (next conversation-stash checkpoint persists the smaller outbox — stash itself is written only on graceful shutdown per ADR-000)
- Deterministic record id (`sha256(chat_id, snapshot_ts, chunk_start/end message_id)`); same-process retry overwrites the same id when the outbox entry is still present
- Startup Chroma hygiene: delete **incomplete** records only when `summary_id` is absent from all in-memory `pending_vectorization` (retry impossible); **complete** records are always kept (including post-crash de-facto flush)
- `outbox_health_threshold` warnings
- encrypt/decrypt identity hooks on the `document` field
- same-process retry tests and incomplete-record cleanup tests

**Out of scope:**
- `recall_conversation` agent skill (TASK-009)
- changes to compression apply (the in-memory outbox push already lands in TASK-006)
- promotion of retrieved summaries into the inline tail
- conversation stash writes on flush (graceful-shutdown-only per ADR-000)
- Chroma collection drop on deleted chats / `delete_user_data` (follow-up task)

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]
- Blocks: [[TASK-009-recall-conversation-skill/task|TASK-009]]

## Notes

Compression never blocks on the vector store — the outbox pattern lands in TASK-006. A summary is invisible to recall until the next flush (≤ one tick) — acceptable per master design.

**Reconciliation (design Decision 6):** complete Chroma records are never deleted at startup. Only incomplete records (missing document or embedding) are removed when no outbox entry remains for retry. `Chat.history` is audit only.

**Follow-up:** drop `chat_{chat_id}` Chroma collections when a chat/user is deleted — tracked as [[TASK-013-chroma-drop-on-delete-user-data/task|TASK-013]].
