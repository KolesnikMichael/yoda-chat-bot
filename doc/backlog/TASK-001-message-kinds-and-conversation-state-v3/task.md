---
id: TASK-001
epic: EPIC-001
title: "message kinds and conversation state v3"
status: todo
priority: high
size: M
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-001: message kinds and conversation state v3

## Description

Introduce the data-model foundation for Chat Context Management: the `Message.kind` field, five new `Conversation` fields (`last_visible_at`, `last_compressed_at`, `visible_messages`, `introduced_users`, `pending_vectorization`), the conversation-stash migration v2→v3 with the fail-fast `infer_kind`, `kind` set by every producer at message-creation time, ingest-time counter updates on visible messages, and loading `ChatCompressionSettings` from `settings.json`. Without this stage, triggers, `user_introduction`, and compression apply are impossible.

## Master design

- [[chat_context_management#Foundational concepts]]
- [[chat_context_management#Persistence and migration]]
- [[chat_context_management#Constants and entry threshold]] (settings loading only)

## Program

Part of the Chat Context Management chain — see the program map in [[EPIC-001-chat-context-management/epic|EPIC-001]].

## Scope boundary

**In scope:**
- `Message.kind` (the six-value `Literal`)
- Five `Conversation` fields + their serialisation into the stash
- `CONVERSATION_STASH_SCHEMA_VERSION` 2→3 and the `infer_kind` migration step (register it in `migration.py:MIGRATIONS` alongside the existing steps). `infer_kind`'s `known_prefixes` must cover **all** current bot-initiated system producers: `SCHEDULED REMINDER:`, `SCHEDULED TASK FAILED:`, `Agent completed a task`, `Ask the user (rephrase naturally` — fail fast on any unknown prefix
- `kind` threaded through the single chokepoint `MemoryCore.add_conversation_line` / `Conversation.add_message`, with each producer passing the correct kind: `Conversation.ensure_system_prompt` (`prompt`), `Perception` (`user`), `Mind._reply_and_send` (`assistant`), `Mind._handle_agent_result` / `Mind.deliver_scheduled_reminder` / `Mind.notify_scheduled_failure` (`task_result`)
- Ingest hook: bump `last_visible_at` and `visible_messages` on `user`/`assistant`
- `ChatCompressionSettings` dataclass + load from settings; **add the `mind.memory.chat_compression` block to `settings.json`** (values per master design). Loaded but not yet used by logic

**Out of scope:**
- `user_introduction`, compression, per-conversation lock, Maintenance, Chroma

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — program map and position in the chain

## Dependencies

- Depends on: —
- Blocks:
  - [[TASK-002-user-introduction-on-ingest/task|TASK-002]]
  - [[TASK-003-compression-window-algorithms-core/task|TASK-003]]
  - [[TASK-004-maintenance-integration-shell/task|TASK-004]]
  - [[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]
  - [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]

## Notes

Foundation of the whole program. After merge, TASK-002, TASK-003 and TASK-004 are unblocked (and can run in parallel).
