---
id: TASK-008
title: "summary store and outbox flush"
status: todo
priority: medium
size: M
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-008: summary store and outbox flush

## Description

Implement the externalised summary store: an `EmbeddingProvider`, a `VectorProvider` (Chroma persistent), and `Maintenance.flush_summary_outbox` — draining `Conversation.pending_vectorization` into Chroma with a deterministic `summary_id` and idempotent retry. Add `outbox_health_threshold` operator warnings. Wire it into `yoda_chat_bot.py` and the Maintenance tick.

## Master design

- [[chat_context_management#Summary store]]
- [[chat_context_management#Persistence flow]]
- [[chat_context_management#Record schema]]
- [[chat_context_management#Security baseline]]

## Program

Part of the Chat Context Management chain — see the program map in [[main#Chat Context Management]].

## Scope boundary

**In scope:**
- `EmbeddingProvider` (OpenRouter `text-embedding-3-small`) behind an API façade so the HTTP call is mockable in tests
- `VectorProvider` (Chroma per-chat collection `chat_{chat_id}`); decide and document the test strategy (ephemeral in-process Chroma vs a fake) and add `chromadb` + the embeddings client to `requirements.txt`, plus the `data/` persistence directory
- `flush_summary_outbox`: embed batch → persist → drain the outbox atomically
- Deterministic record id (`sha256(chat_id, snapshot_ts, chunk_start/end message_id)`)
- `outbox_health_threshold` warnings
- encrypt/decrypt identity hooks on the `document` field
- crash-recovery / retry tests

**Out of scope:**
- `recall_conversation` agent skill (TASK-009)
- changes to compression apply (the outbox push already lands in TASK-006)
- promotion of retrieved summaries into the inline tail

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[main#Chat Context Management]] — program map and position in the chain

## Dependencies

- Depends on: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]
- Blocks: [[TASK-009-recall-conversation-skill/task|TASK-009]]

## Notes

Compression never blocks on the vector store — the outbox pattern lands in TASK-006. A summary is invisible to recall until the next flush (≤ one tick) — acceptable per master design.
