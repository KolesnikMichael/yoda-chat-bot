---
id: TASK-006
doc: requirements
updated: 2026-06-17
---

# TASK-006: compression apply and size trigger — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) reaches its first user-visible milestone here: long conversations compress inline when they exceed the size threshold, replacing older messages with a durable `summary` block and extracted profile deltas — without Chroma or recall. Upstream tasks delivered the data model ([[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]), `user_introduction` lifecycle ([[TASK-002-user-introduction-on-ingest/task|TASK-002]]), pure window/trigger algorithms ([[TASK-003-compression-window-algorithms-core/task|TASK-003]]), the `Maintenance` periodic shell with dry-run stubs ([[TASK-004-maintenance-integration-shell/task|TASK-004]]), and `SummarizerProvider` ([[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]). Nothing yet performs snapshot → transform → graft+merge apply or wires a live trigger.

This task delivers the full compression apply pipeline per [[chat_context_management#Compression apply]]: per-conversation locking, transformation steps 1–10 on a deep-copied working `Conversation`, graft+merge with `new_arrivals` reconciliation, inline `summary` messages, FIFO eviction into `pending_vectorization`, `Chat.history` audit entries, and **size-trigger-only** wiring in `Maintenance.compress_conversations`. The summarisation LLM call stays delegated to `SummarizerProvider`; profile deltas are applied via `MemoryProvider.update_user_profile` (TASK-000 merge semantics) in transformation step 5 **before** `user_introduction` refresh (step 8), reusing the TASK-002 Core helper for strip/refresh/merge reconciliation.

Stakeholders: users in long-running chats (lower token cost, preserved gist), operators (audit trail, bounded inline summary count), and downstream tasks ([[TASK-007-timeout-trigger-wiring/task|TASK-007]] reuses apply; [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] drains `pending_vectorization`).

## Functional requirements

### FR-1: Per-conversation compression lock shared with ingest

Concurrent ingest and compression must not observe torn message lists or partially merged state.

**Acceptance criteria:**
- [ ] Each `Conversation` (keyed by `chat_id`) has a dedicated `asyncio.Lock` used for compression snapshot, compression apply, and message ingest that mutates `Conversation.messages` or trigger bookkeeping (`visible_messages`, `last_visible_at`, `introduced_users`).
- [ ] **Snapshot** (record `N_old`, `deep_copy(live)`, `snapshot_ts`) runs entirely under the lock — three cheap operations only.
- [ ] **Apply** (graft, derived-field merge, `new_arrivals` reconciliation, persistence kick-off) runs entirely under the lock.
- [ ] The LLM call and the rest of transformation on the copy run **without** holding the lock, so ingest is not blocked during summarisation.
- [ ] Under the apply lock, `len(live.messages) >= N_old` is asserted (tripwire for future in-place mutation); violation fails fast rather than producing a corrupt graft.
- [ ] `Mind` ingest paths that append messages acquire the same per-`chat_id` lock before mutating the live conversation.

### FR-2: Snapshot contract

Every compression run starts from an indivisible snapshot of the live conversation.

**Acceptance criteria:**
- [ ] At snapshot time: `N_old = len(live.messages)` and `copy = deep_copy(live)` capture a self-contained working `Conversation` including `messages`, `visible_messages`, `last_visible_at`, `last_compressed_at`, `introduced_users`, and `pending_vectorization`.
- [ ] `snapshot_ts` is recorded once at snapshot (float epoch seconds, subsecond precision) and reused as `last_compressed_at` on successful commit and as the audit entry `ts`.
- [ ] After snapshot, ingest may append to `live.messages` at indices `>= N_old`; indices `0..N_old-1` are treated as immutable until apply (append-only assumption).
- [ ] `new_arrivals` at apply time is exactly `live.messages[N_old:]`.

### FR-3: Size-trigger window selection and chunk construction (transformation step 1)

Apply uses the size-trigger algorithm only; timeout window selection is not invoked in this task.

**Acceptance criteria:**
- [ ] On `copy.messages`, window selection calls `CompressionCore.select_size_trigger_window` (no timeout fallback when it returns `None`).
- [ ] When `select_size_trigger_window` returns `None`, the run aborts as a no-op: live conversation, profiles, `Chat.history`, and counters are unchanged; `last_compressed_at` is not updated.
- [ ] Split semantics: messages `[0:split)` form the compressible region input; `[split:]` is the live tail retained raw before chunk shaping.
- [ ] The compressible chunk excludes the leading `prompt` message and any contiguous existing `summary` blocks at the head of `[0:split)` before further transformation — they are not passed to summarisation and are not replaced by the new summary block.
- [ ] `chunk_visible_count` is the count of messages in the final summariser chunk whose `kind` is `user` or `assistant` (per `CompressionCore.is_visible`).
- [ ] `chunk_start_message_id` and `chunk_end_message_id` are taken from the first and last messages in the summariser chunk that carry a non-`None` `message_id` (design may define fallback when ids are absent; behaviour must be deterministic and tested).

### FR-4: `user_introduction` strip before summarisation (transformation step 2)

Profile snapshot markers are removed from the summariser payload.

**Acceptance criteria:**
- [ ] Every `user_introduction` message in the compressible chunk is removed before `SummarizerProvider.summarise` is called.
- [ ] `removed_users` is the set of `user_id` values from stripped introductions (non-`None` `user_id` only).
- [ ] Stripped introductions do not appear in the `chunk` argument passed to `summarise`.
- [ ] In tests with a fixture where compressed `user`-kind authors match stripped introductions, `removed_users` equals the set of `user_id`s of `user`-kind messages in the chunk (invariant asserted in implementation).

### FR-5: Summariser invocation (transformation steps 3–4)

One LLM call per successful run, delegated to `SummarizerProvider`.

**Acceptance criteria:**
- [ ] The Integration calls `await summarizer_provider.summarise(chunk, participant_profiles)` with the stripped chunk from FR-4.
- [ ] `participant_profiles` maps each mechanical participant (`SummarizerResult.participants` or pre-call `SummarizerCore.extract_participants`) to the current `UserProfile` from `MemoryProvider.get_user_profile(user_id, chat_id)` — profiles are context for the LLM only; the Provider does not load them.
- [ ] On `SummarizerValidationError`, `json.JSONDecodeError`, or any summariser failure, the run aborts as a no-op: no graft, no counter updates, no profile writes, no `Chat.history` entry; live state matches pre-run.
- [ ] Successful `SummarizerResult` fields (`summary`, `topics`, `participants`, `skills`, `profile_updates`) are consumed by subsequent transformation steps; record-schema fields (`summary_id`, chunk ids/count, `created_at`) are computed by the apply Integration, not by the Provider.

### FR-6: Profile delta application before introduction refresh (transformation step 5)

Compression-time profile updates commit before step 8 builds fresh introductions.

**Acceptance criteria:**
- [ ] For each `(user_id, delta)` in `SummarizerResult.profile_updates`, the Integration calls `MemoryProvider.update_user_profile(user_id, chat_id, delta)` (or equivalent wrapper accepting the delta dict shape from TASK-005).
- [ ] Profile updates persist to the user-profile store directly — they are not stored on `copy`.
- [ ] All profile updates complete **before** transformation step 8 (`user_introduction` refresh); tests demonstrate refreshed introduction text reflects a scalar change applied in step 5.
- [ ] Empty `profile_updates` skips profile writes without error.
- [ ] `SummarizerProvider` is never called from inside `MemoryProvider` and does not perform these writes (IODA).

### FR-7: Inline `summary` block insertion (transformation step 6)

The compressible chunk is replaced by one new `summary` message.

**Acceptance criteria:**
- [ ] The chunk region in `copy.messages` (after FR-3 head skipping, post-strip) is replaced by a single `Message` with `kind="summary"` and `role="system"` (exact `text` envelope is a design choice but must round-trip through stash v3).
- [ ] `summary_id` is deterministic: `sha256` hex over `(chat_id, snapshot_ts, chunk_start_message_id, chunk_end_message_id)` per [[chat_context_management#Deterministic record id]].
- [ ] The summary message `text` carries the narrative `SummarizerResult.summary` (and any metadata encoding the design chooses for inline readers).
- [ ] After step 6, `copy.messages` order is: `[prompt, …existing summaries…, new_summary, …live tail…]` consistent with variant C (parallel summaries, never re-summarised).

### FR-8: `MAX_SUMMARY_COUNT` FIFO eviction and outbox push (transformation step 7)

Inline summary count stays bounded; evicted blocks queue for later vectorisation.

**Acceptance criteria:**
- [ ] After inserting the new summary, if the count of `kind == "summary"` messages in `copy.messages` exceeds `ChatCompressionSettings.max_summary_count`, the oldest summary block(s) at the head of the message list are removed — same count as added in this run (typically one).
- [ ] Each evicted summary produces one `SummaryOutboxEntry` appended to `copy.pending_vectorization` with fields: `summary_id`, `document` (summary text), `created_at` (= `snapshot_ts`), `chunk_start_message_id`, `chunk_end_message_id`, `chunk_visible_count`, `participants`, `skills`, `topics`, and `added_at` (ISO-8601 UTC of when that summary was originally added inline — from the evicted block's metadata or audit data).
- [ ] When no eviction is required, `copy.pending_vectorization` is unchanged by step 7.
- [ ] `Maintenance.flush_summary_outbox` remains a no-op in this task — entries accumulate only.
- [ ] Evicted summaries are absent from `copy.messages` but present in `copy.pending_vectorization` after a successful apply.

### FR-9: `user_introduction` refresh on the copy tail (transformation step 8)

Reintroduce profile snapshots for users whose introductions were compressed away.

**Acceptance criteria:**
- [ ] For each `user_id ∈ removed_users`, the Integration scans `copy.messages` **after** the just-inserted summary for that user's first `kind == "user"` message.
- [ ] **Found:** build introduction text via the same snapshot formatter as TASK-002 (`MemoryCore.format_user_profile_snapshot` on the post-step-5 profile) and insert `user_introduction` immediately before that message using `MemoryCore.ensure_user_introductions_in_range` on the appropriate half-open range (or equivalent call into the same helper).
- [ ] **Not found:** remove `user_id` from `copy.introduced_users` (lazy re-introduction on next ingest per TASK-002).
- [ ] The helper from TASK-002 FR-4 is reused — no parallel introduction-placement implementation.
- [ ] Step 8 operates only on the snapshot tail; it does not process `new_arrivals` (FR-11).

### FR-10: Derived field updates on the copy (transformation step 9)

Bookkeeping on `copy` reflects a successful compression of the snapshot.

**Acceptance criteria:**
- [ ] `copy.visible_messages -= chunk_visible_count` (from FR-3).
- [ ] `copy.last_compressed_at = snapshot_ts`.
- [ ] `copy.introduced_users` reflects mutations from step 8 only (no full rebuild unless the helper adds entries).
- [ ] After step 9, `copy` represents the conversation state that would have resulted had no concurrent ingest occurred.

### FR-11: `Chat.history` compression audit entry (transformation step 10)

Each successful run appends a structured audit record.

**Acceptance criteria:**
- [ ] A `compression` event is appended to `Chat.history` for the `chat_id` per [[chat_context_management#Chat.history schema]].
- [ ] Envelope fields: `ts` (= `snapshot_ts` as ISO-8601 UTC), `event` = `"compression"`, `added` with `summary_id`, `visible_count` (= `chunk_visible_count`), `from_ts` / `to_ts` (ISO-8601 from first/last **visible** messages in the summariser chunk).
- [ ] `evicted` is always present: a list (possibly empty) of `{"summary_id", "added_at"}` for each summary moved to `pending_vectorization` in step 7.
- [ ] The audit entry is appended to in-memory `Chat.history` and persisted to the `chats` Redis hash as part of successful apply (audit metadata only — event ids, counts, timestamps; no message bodies). Conversation stash is **not** written on apply ([[ADR-000-sensitive-data-persistence]]).

### FR-12: Apply — graft, merge, and `new_arrivals` reconciliation

The live conversation receives the transformed copy plus messages that arrived during the LLM call. Apply commits **in-memory only**; durability of message replicas waits for graceful shutdown ([[ADR-000-sensitive-data-persistence]], [[chat_context_management#Crash recovery]]).

**Acceptance criteria:**
- [ ] **Graft:** under the apply lock, `live.messages = copy.messages + new_arrivals` where `new_arrivals = live.messages[N_old:]`.
- [ ] **Merge counters:** `live.last_compressed_at = copy.last_compressed_at`, `live.visible_messages = copy.visible_messages + visible_count(new_arrivals)`, where `visible_count` counts only `user` and `assistant` kinds in `new_arrivals`.
- [ ] **Merge bookkeeping:** `live.introduced_users = copy.introduced_users` then reconcile introductions on `new_arrivals` using the same contract as [[chat_context_management#Apply: graft + merge]]: (a) already introduced with marker in arrivals → no-op; (b) already introduced without marker in arrivals → no-op; (c) not introduced but marker present in arrivals → add to `introduced_users`; (d) not introduced, no marker, but `user_id` was in `removed_users` and has a `user` message in arrivals → build introduction before first such message and add to `introduced_users`.
- [ ] Reconciliation on `new_arrivals` reuses `MemoryCore.ensure_user_introductions_in_range` (same helper as step 8, different index range).
- [ ] `live.pending_vectorization` is replaced with `copy.pending_vectorization` (outbox reflects eviction from this run; held in-memory on `Conversation` until the next graceful-shutdown stash checkpoint).
- [ ] `Chat.history` includes the new audit line from step 10 (persisted to the `chats` hash per FR-11).
- [ ] Successful apply does **not** call `save_conversation_stash`.

### FR-13: Post-apply invariant

The live tail must satisfy the `user_introduction` contract after every successful apply.

**Acceptance criteria:**
- [ ] For every distinct `user_id` with a `kind == "user"` message in the tail after the last `summary` block in `live.messages`: `user_id ∈ live.introduced_users` **and** a `user_introduction` for that `user_id` immediately precedes that user's first such message in the tail.
- [ ] Automated tests assert this invariant on fixtures covering: private chat, group chat with multiple `removed_users`, and the graft edge case (user in `removed_users`, message arrived during LLM call, ingest skipped introduction because pre-apply `live.introduced_users` still had the user).

### FR-14: Size-trigger wiring in `Maintenance.compress_conversations`

Replace dry-run logging with live apply for the size trigger only.

**Acceptance criteria:**
- [ ] `Maintenance` receives `SummarizerProvider` (constructed in `yoda_chat_bot.py` per master design) in addition to existing dependencies.
- [ ] On each Maintenance tick, for each conversation from `MemoryProvider.iter_conversations()`: when `CompressionCore.should_fire_size_trigger(visible_messages, settings)` is `True`, invoke the full apply pipeline for that conversation (FR-1–FR-13).
- [ ] When the size trigger is `False`, no apply is attempted for that conversation on that tick.
- [ ] Timeout trigger: `CompressionCore.should_evaluate_timeout_trigger` may still be evaluated for logging if the existing dry-run behaviour is retained, but **timeout must not invoke apply** in this task — apply runs only on size trigger.
- [ ] When size trigger fires but window selection or summarisation aborts (no-op paths), the conversation is left unchanged and the tick continues with other conversations.
- [ ] Successful compression logs at **debug** with `chat_id` and trigger type; no message text, summary body, or profile payloads at info level or above.

### FR-15: Automated tests — invariants and concurrent ingest

Behaviour is locked before TASK-007/008 build on this pipeline.

**Acceptance criteria:**
- [ ] Unit/integration tests cover: happy-path size-trigger apply (messages replaced by summary, counters decremented, `last_compressed_at` set); `MAX_SUMMARY_COUNT` eviction producing `pending_vectorization` entries and `Chat.history.evicted`; profile delta in step 5 visible in step-8 introduction text; summariser failure → no state change.
- [ ] **Concurrent ingest test:** with a fake `SummarizerProvider` or fake LLM that blocks until test code appends messages to the live conversation, after apply `live.messages` equals `copy.messages + injected_arrivals` and FR-13 holds, including graft case (d) from FR-12.
- [ ] `python -m pytest` from the project root passes with the new tests.

## Constraints & assumptions

- **Constraint (IODA):** Snapshot/transform orchestration is Integration work (`Maintenance` +/or `MemoryProvider` apply entry point per design); window rules stay in `CompressionCore`; summarisation in `SummarizerProvider`; introduction placement in `MemoryCore.ensure_user_introductions_in_range`; Providers do not call other Providers — the Integration passes profile snapshots into `summarise` and calls `update_user_profile` itself.
- **Constraint (delivery profile):** Epic `internal_compat: none` — no acceptance criteria for partial deploy states between member tasks on the shared branch. Epic `external_contract: migrate-on-merge` — first compression on upgraded v3 conversations uses counters from TASK-001 migration; no new stash schema version in this task.
- **Constraint (ADR-000):** Apply updates in-memory `Conversation` state only — no `save_conversation_stash` on apply or Maintenance tick. User message replicas reach Redis only via graceful-shutdown conversation stash ([[ADR-000-sensitive-data-persistence]]).
- **Constraint:** Fail fast on missing `chat_type`, lock assertion failure, and summariser validation errors — no partial apply or silent skip of profile/history audit writes on the success path.
- **Constraint:** Two algorithms, not one — timeout window selection and apply are out of scope; size-trigger halving must never run as a fallback inside timeout logic (timeout not wired here).
- **Constraint:** Variant C — never re-summarise existing inline `summary` blocks; each run adds at most one new summary.
- **Constraint:** `logger.debug` for operational detail that may include `chat_id`; user message content and profile snapshots only at debug and truncated per coding guidelines.
- **Assumption:** [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] through [[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]] are complete: `Message.kind`, `SummaryOutboxEntry`, `SummarizerProvider.summarise`, `CompressionCore` predicates/windows, `Maintenance` tick loop, and `MemoryCore.ensure_user_introductions_in_range` behave as specified.
- **Assumption:** `Chat` metadata (including `history`) is loaded and saved via `StorageApi` `chats` hash; `Conversation` stash does not embed `Chat.history` — the apply Integration merges audit lines into persisted `Chat.history`.
- **Assumption:** Summary inline `text` format and whether `summary_id` is duplicated inside the `Message` are design choices as long as eviction and audit entries can recover `summary_id` and document text for `SummaryOutboxEntry`.
- **Assumption:** Multiple conversations may fire the size trigger on the same tick; each is processed independently (sequential per tick is acceptable unless design parallelises with per-chat locks).
- **Assumption:** `flush_summary_outbox` stays a no-op; outbox depth warnings ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]) are not required here.

## Out of scope

- Timeout-trigger apply wiring ([[TASK-007-timeout-trigger-wiring/task|TASK-007]] — predicate may log; must not apply).
- `SummarizerProvider` internals, prompt prose, or envelope validation rules ([[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]).
- Chroma, embeddings, real `flush_summary_outbox`, outbox health warnings ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]).
- `recall_conversation` agent skill ([[TASK-009-recall-conversation-skill/task|TASK-009]]).
- Changes to `CompressionCore` window/trigger algorithms ([[TASK-003-compression-window-algorithms-core/task|TASK-003]]).
- New `Message` / `Conversation` stash schema versions or v2→v3 migration changes ([[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]).
- Re-summarising or merging existing inline summaries (variant B).
- `save_conversation_stash` on apply, ingest, or Maintenance tick ([[ADR-000-sensitive-data-persistence]]).
- Splitting the apply pipeline into separately deployable intermediate states (task note: snapshot/transform/graft invariants admit no valid partial milestone).
