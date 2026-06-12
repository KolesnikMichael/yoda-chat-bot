---
id: TASK-001
doc: requirements
updated: 2026-06-12
---

# TASK-001: message kinds and conversation state v3 — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) needs a data-model foundation before compression triggers, `user_introduction`, or apply pipelines can land. Today `Message` has no `kind`, `Conversation` carries only `chat_id` and `messages`, and the conversation stash is schema version 2 with no migration path to typed message kinds or trigger bookkeeping fields.

This task introduces `Message.kind` (six-value `Literal`), five new `Conversation` fields persisted in the stash, a fail-fast v2→v3 migration with `infer_kind`, explicit `kind` assignment at every message producer, ingest-time updates to visible-message counters, and startup loading of `ChatCompressionSettings` from `settings.json`. Compression logic itself does not run yet — settings are loaded and held for downstream tasks ([[TASK-003-compression-window-algorithms-core/task|TASK-003]] onward).

Stakeholders: operators upgrading an existing deployment (migration must not silently mis-label system traffic), and later tasks that depend on accurate `kind`, counters, and settings ([[TASK-002-user-introduction-on-ingest/task|TASK-002]] through [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]).

## Functional requirements

### FR-1: `Message.kind` field

Every stored message must carry an explicit, statically typed kind set at creation time.

**Acceptance criteria:**
- [ ] `Message` declares `kind` with type `Literal["prompt", "user", "assistant", "task_result", "user_introduction", "summary"]`.
- [ ] `kind` is included in stash serialisation (`conversations_to_stash_dict` / `stash_dict_to_conversations`) and round-trips without loss.
- [ ] `Message.to_llm_dict()` behaviour is unchanged — `kind` is metadata for storage and trigger logic, not sent to the LLM as an extra field unless an existing code path already serialises the full dataclass (it must not break LLM message shape).

### FR-2: Five `Conversation` state fields

`Conversation` gains the bookkeeping fields defined in [[chat_context_management#Conversation state fields]].

**Acceptance criteria:**
- [ ] `Conversation` declares `last_visible_at: float` (default `0.0`), `last_compressed_at: float` (default `0.0`), `visible_messages: int` (default `0`), `introduced_users: set[int]` (default empty set), and `pending_vectorization: list` (default empty list; element type is the summary-outbox record — exact dataclass shape is a design decision, but the field must exist and round-trip empty lists).
- [ ] A newly created `Conversation` (no prior stash) has these defaults without caller initialization.
- [ ] `introduced_users` serialises to a JSON array of integers in the stash and deserialises back to `set[int]`.
- [ ] `pending_vectorization` serialises as a JSON array (empty `[]` for all conversations after migration and for new chats in this task).

### FR-3: Conversation stash schema version 3

The Redis conversation stash wire format bumps to v3 and persists the new conversation fields alongside messages.

**Acceptance criteria:**
- [ ] `CONVERSATION_STASH_SCHEMA_VERSION` is `3`.
- [ ] Each conversation entry in the stash JSON includes `chat_id`, `messages` (each with `kind`), and all five fields from FR-2.
- [ ] Saving and restoring a stash at schema version 3 reproduces identical in-memory `Conversation` objects (messages order, kinds, counters, sets, outbox list).
- [ ] Stashes at schema version 2 are upgraded through the migration step in FR-4 on restore, not read natively.

### FR-4: Migration v2→v3 with fail-fast `infer_kind`

On startup stash restore, legacy v2 conversations are migrated once to v3 before entering normal operation.

**Acceptance criteria:**
- [ ] `migration.py` registers `_conversation_stash_v2_to_v3` in `MIGRATIONS["conversation_stash"][2]`.
- [ ] For each message in order, `infer_kind` assigns: `assistant` if `role == "assistant"`; `prompt` if it is the first message in the list; `user` if `user_id is not None`; otherwise (system role, no `user_id`, not first) `task_result` only when `text.startswith` matches one of: `"SCHEDULED REMINDER:"`, `"SCHEDULED TASK FAILED:"`, `"Agent completed a task"`, `"Ask the user (rephrase naturally"`.
- [ ] Any system message that fails the prefix check raises `MigrationError` (or equivalent dedicated exception) with enough context to locate the message (`chat_id`, message index or id, and a text prefix); migration aborts and the stash key is left in place (existing restore failure behaviour).
- [ ] In the same pass over migrated messages: `introduced_users` is the set of distinct `user_id` values among messages with `kind == "user"`; `visible_messages` is the count of messages with `kind` in `("user", "assistant")`; `last_visible_at` is the maximum parsed timestamp among visible messages, or `0.0` if none.
- [ ] After migration: `last_compressed_at` is set to `0.0`; `pending_vectorization` is set to `[]`; root `schema_version` is `3`.
- [ ] Pre-migration stashes containing only legacy `prompt` / `user` / `assistant` / `task_result`-equivalent content (no `summary`, no `user_introduction`) migrate successfully in tests representing typical production shapes.

### FR-5: `kind` threaded through the message-creation chokepoint

All new messages must receive `kind` at the single creation path — no downstream inference in normal operation.

**Acceptance criteria:**
- [ ] `Conversation.ensure_system_prompt` creates its message with `kind="prompt"`.
- [ ] `Conversation.add_message` accepts a required `kind` parameter and stores it on the `Message`.
- [ ] `MemoryCore.add_conversation_line` accepts a required `kind` parameter and passes it through to `ensure_system_prompt` / `add_message` (the system prompt path uses `prompt`; the appended line uses the supplied kind).
- [ ] Call sites that bypass `add_conversation_line` for message append (if any remain) are eliminated or updated — every append goes through the chokepoint.

### FR-6: Correct `kind` from each producer

Each message producer passes the kind defined in [[chat_context_management#Message kinds]].

**Acceptance criteria:**
- [ ] `Mind.process_message_batch` (perceived user lines from `Perception`) passes `kind="user"` even though perception returns `role="system"`.
- [ ] `Mind._reply_and_send` passes `kind="assistant"` for each assistant reply part.
- [ ] `Mind._handle_agent_result` passes `kind="task_result"` for agent outcome and clarification lines.
- [ ] `Mind.deliver_scheduled_reminder` passes `kind="task_result"`.
- [ ] `Mind.notify_scheduled_failure` passes `kind="task_result"`.
- [ ] No producer in this task emits `user_introduction` or `summary` kinds (reserved for later tasks); tests or inspection confirm only the five active kinds appear in new traffic.

### FR-7: Visible-message ingest counters

When a visible message is ingested, conversation activity counters update in the same code path as the append.

**Acceptance criteria:**
- [ ] A message is **visible** if `kind` is `"user"` or `"assistant"` (per [[chat_context_management#Visibility]]).
- [ ] On ingest of a visible message, `visible_messages` increments by exactly `1`.
- [ ] On ingest of a visible message, `last_visible_at` is set to the maximum of its current value and the new message's timestamp expressed as Unix epoch seconds (float, subsecond precision preserved where the source timestamp allows).
- [ ] Ingest of non-visible kinds (`prompt`, `task_result`, and the reserved `user_introduction` / `summary`) does **not** change `visible_messages` or `last_visible_at`.
- [ ] `last_compressed_at` and `introduced_users` are not modified by ingest in this task (owned by compression / TASK-002 respectively).

### FR-8: `ChatCompressionSettings` loaded at startup

Compression constants are loaded from configuration and available to wiring, but no trigger or compression logic consumes them yet.

**Acceptance criteria:**
- [ ] A `ChatCompressionSettings` dataclass (or equivalent Data type) exposes fields matching `settings.json → mind.memory.chat_compression` keys 1:1: `size_trigger_threshold`, `min_chunk_length`, `max_summary_count`, `gap_to_trigger_ratio`, `quiet_runs_before_compression` (with `private` and `group` integer sub-keys), and `outbox_health_threshold`.
- [ ] Default values in the repo's `settings.json` match the master design block ([[chat_context_management#Constants and entry threshold]]): `300`, `30`, `30`, `0.5`, `{ "private": 8, "group": 8 }`, `10`.
- [ ] Startup loading fails fast (`ValueError` or equivalent) if the `mind.memory.chat_compression` block or any required key is missing — no silent defaults beyond dataclass defaults for optional future keys.
- [ ] The loaded settings object is constructed in `yoda_chat_bot.py` (or passed into components that will need it later) but is **not** referenced by compression, maintenance, or ingest logic in this task.

## Constraints & assumptions

- **Constraint:** Follow IODA — Data changes in `Message` / `Conversation` / `ChatCompressionSettings`; migration and stash logic in `MemoryCore` / `migration.py` (Core); persistence in `MemoryProvider` (Provider); producer call sites in `Mind` and `Conversation` methods (Integration / Data).
- **Constraint:** Migration is fail-fast — never default unknown system prefixes to `task_result`.
- **Constraint:** `kind` is set at creation time only; runtime code must not infer kind from `role` or text except inside the one-time v2→v3 migration.
- **Constraint:** Additive where possible — LLM-facing message shape and existing chat flows continue to work; visible behaviour to users is unchanged.
- **Assumption:** Production v2 stashes contain no `summary` or `user_introduction` messages, so migration only infers the four legacy shapes plus the four known bot-initiated prefixes.
- **Assumption:** `Perception` always sets `user_id` on user-originated lines; user kind is assigned by the caller, not by re-inspecting role.
- **Assumption:** Message `timestamp` strings are parseable to epoch floats consistently in migration and ingest (exact parser is a design choice; behaviour must match between migration backfill and live ingest).
- **Assumption:** [[TASK-000-compression-prerequisites/task|TASK-000]] may land before or in parallel; agent-result lines already include `Tools used: …` but migration keys off the `"Agent completed a task"` prefix, not the tools clause.
- **Assumption:** `pending_vectorization` remains empty in operation until compression apply (TASK-006+); this task only reserves the field and wire format.

## Out of scope

- Lazy `user_introduction` insertion, `introduced_users` maintenance on ingest, or profile snapshot content ([[TASK-002-user-introduction-on-ingest/task|TASK-002]]).
- `CompressionCore`, trigger predicates, window selection, or any use of loaded compression settings ([[TASK-003-compression-window-algorithms-core/task|TASK-003]] onward).
- `Maintenance` integration, periodic compression loop, per-conversation lock ([[TASK-004-maintenance-integration-shell/task|TASK-004]]).
- `SummarizerProvider`, profile extraction apply, creating `summary` messages ([[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]], [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]).
- Chroma, embeddings, `flush_summary_outbox`, `recall_conversation` skill ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]], [[TASK-009-recall-conversation-skill/task|TASK-009]]).
- Decrementing `visible_messages` or updating `last_compressed_at` on compression apply (compression tasks).
- Populating `pending_vectorization` with real summary records (compression apply).
