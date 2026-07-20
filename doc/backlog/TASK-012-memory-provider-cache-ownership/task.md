---
id: TASK-012
epic: 
title: "memory provider cache ownership"
status: todo
priority: low
size: S-M
created: 2026-06-18
updated: 2026-06-18
tags:
  - memory
  - ioda
---

# TASK-012: memory provider cache ownership

## Description

Follow-up from [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] close-out and subsequent design discussion.

`MemoryProvider` owns the in-memory `_conversations` cache, but exposes it as a **low-level CRUD trio** — `get_conversation` / `save_conversation` / `forget_conversation` — each hopping through `MemoryCore.conversation_key` (`str(chat_id)`) for a wire-format concern that belongs at the stash boundary. Meanwhile mutation paths split responsibility: `append_*` / `commit_compression` hold the lock but do not always register; `Mind` must `get` → pass a mutable `Conversation` handle → `save` after every append. When the object already came from `get_conversation`, `save` is a no-op re-put (including in `commit_compression`). `forget_conversation` is the symmetric half-line cache drop, called directly from `DeleteUserDataTool` alongside Redis deletes.

`save_conversation_stash` is the real durable write (graceful shutdown only, [[ADR-000-sensitive-data-persistence]]). Naming blurs in-memory cache vs durability.

IODA note: Integration → Provider calls are allowed; the issue is **encapsulation** — callers should not manage cache object lifecycle or see raw CRUD. See [[requirements]] for alternatives.

Pick and implement a cleaner Provider cache contract. Not urgent — behaviour is correct today.

## Scope boundary

**In scope:**
- Cache **CRUD trio** (`get` / `save` / `forget`) — visibility, naming, `conversation_key` hop
- Register-after-mutate under lock; drop redundant external `save` from `Mind` / `commit_compression`
- Optional `chat_id`-only public API (Mind stops passing `Conversation` handles)
- Optional high-level `forget` for GDPR path (`delete_user_data_tool`) vs public `forget_conversation`
- Rename for clarity (`register` vs `stash`)
- Tests and fakes updated

**Out of scope:**
- `save_conversation_stash` policy or frequency (ADR-000 unchanged)
- `Conversation` / stash schema changes
- New top-level Integration class
- Moving business logic from Core into Provider

## Related documents

- [[requirements]] — problem statement and solution alternatives
- [[design]] — chosen approach (filled at design time)
- [[plan]] — implementation plan
- [[review]] — plan-compliance gate (verdict + findings)
- [[ADR-000-sensitive-data-persistence]]

## Dependencies

- Depends on: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] (surfaces pattern in `commit_compression`; refactor can proceed independently)
- Blocks:

## Notes

Standalone memory/Provider hygiene — not part of [[EPIC-001-chat-context-management/epic|EPIC-001]].
`DeleteUserDataTool` is a second external caller of cache CRUD (`forget_conversation`) — include in design review.
Defer until a natural touch of `memory.py` / `mind.py`.
