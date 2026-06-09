---
id: TASK-009
epic: EPIC-001
title: "recall conversation skill"
status: todo
priority: medium
size: S
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-009: recall conversation skill

## Description

Add the agent skill `recall_conversation(query, k, optional filters)` — embed the query → Chroma search in the per-chat collection → return the top-K evicted summaries to the agent as a system message / `task_result`. Yoda does not call recall on every turn; only on an explicit agent task. Retrieved text is **not** promoted into the inline summary list.

## Master design

- [[chat_context_management#Recall path]]

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- skill spec + implementation: `recall_conversation(query, k=5, filters?)`, following the agent skill conventions in `yoda/mind/agent/AGENTS.md`
- `EmbeddingProvider.embed` + `VectorProvider.search` with optional filters (`participants`, `skills`, `topics`, `created_at` range)
- agent-side wiring (skill registration, public description if needed)
- tests: recall finds an evicted summary; the result is visible via `task_result`, not in the inline tail

**Out of scope:**
- promotion of retrieved summaries into `Conversation.messages`
- in-process LRU cache keyed by `summary_id`
- changes to compression / outbox / apply

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on: [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]
- Blocks: —

## Notes

The program's final stage. A cold path — not a blocker for launching compression (the milestone is at TASK-006).
