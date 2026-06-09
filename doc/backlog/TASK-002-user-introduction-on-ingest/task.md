---
id: TASK-002
epic: EPIC-001
title: "user introduction on ingest"
status: todo
priority: medium
size: S
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-002: user introduction on ingest

## Description

Implement the lazy insertion of `user_introduction` — a non-visible system message carrying a `UserProfile` snapshot — immediately before a participant's first `user` message in the live tail. Maintain `introduced_users` for O(1) lookup on ingest. The same code path serves both private and group chats.

## Master design

- [[chat_context_management#user_introduction lifecycle]]
- [[chat_context_management#Insertion on message ingest]]

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- `user_introduction` message format (`kind`, content built from `UserProfile`, including `skill_preferences`)
- Lazy insert before a participant's first `user` message
- Update `introduced_users` on ingest
- A **reusable Core helper** ("ensure a `user_introduction` precedes each user's first `user`-kind message in a given range") parameterised by range, designed up front so TASK-006 can reuse it for the compression refresh (step 8) and the graft/merge reconciliation on `new_arrivals` without refactoring
- Tests: private chat, group chat, repeated messages from the same user

**Out of scope:**
- `user_introduction` refresh during compression (transformation steps 2/8)
- graft+merge reconciliation on `new_arrivals`
- compression triggers

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on:
  - [[TASK-000-compression-prerequisites/task|TASK-000]] (the `user_introduction` snapshot includes `UserProfile.skill_preferences`)
  - [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]
- Blocks: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]

## Notes

Can run in parallel with TASK-003 and TASK-004 after TASK-001 (and TASK-000) merge.
