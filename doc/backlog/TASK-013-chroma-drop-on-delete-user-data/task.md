---
id: TASK-013
epic: EPIC-001
title: "chroma drop on delete user data"
status: todo
priority: medium
size: S
created: 2026-07-19
updated: 2026-07-19
tags:
  - chat-context
  - privacy
---

# TASK-013: chroma drop on delete user data

## Description

Follow-up from [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] Decision 11.

`DeleteUserDataTool` clears Redis user/profile/job/private-chat keys and drops the in-memory private DM via `forget_conversation`, but never touches Chroma. After TASK-008, flushed summary narratives remain in `chat_{user_id}` collections — a privacy leak relative to the manage_user_data “forgotten” promise. Add `VectorProvider.delete_collection(chat_id)` (or equivalent), wire it into `DeleteUserDataTool` for the private-chat id (`user_id`), update skill copy if needed, and cover with tests. Scope matches today's tool: private DM only — group chats are already out of `delete_user_data`.

## Master design

- [[chat_context_management#Summary store]]
- [[chat_context_management#Security baseline]]
- [[ADR-000-sensitive-data-persistence]]

## Program

Part of the Chat Context Management chain — see [[EPIC-001-chat-context-management/epic|EPIC-001]]. Privacy lifecycle for the vector store; not on the critical path to TASK-009 recall, but should land before epic merge so deleted users leave no Chroma residue.

## Scope boundary

**In scope:**
- `VectorProvider` API to drop a per-chat collection (no-op if absent)
- Inject provider into `DeleteUserDataTool`; call on successful private-chat delete path
- Wiring in `yoda_chat_bot.py`
- Tests: collection gone after delete; absent collection is safe; existing delete-user-data cases still pass
- Update `manage_user_data` skill wording if it lists deleted artifacts

**Out of scope:**
- Dropping collections for group chats the user participated in
- Startup sweep of orphan collections with no Redis `chats` entry (broader lifecycle)
- Real AES-GCM encryption; `recall_conversation` (TASK-009)
- Relocating Redis orchestration out of the tool ([[TASK-012-memory-provider-cache-ownership/task|TASK-012]])

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[review]] — plan-compliance gate (verdict + findings)
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — epic decomposition and master design
- [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] — originating deferral

## Dependencies

- Depends on: [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]
- Blocks:

## Notes

Discovered / deferred during TASK-008 close-out. Size **S**: Provider method + tool injection + wiring + tests + skill copy — privacy-relevant enough for a full task pipeline, not a `main.md` Fix one-liner. May touch the same tool as TASK-012; coordinate if both are in flight.
