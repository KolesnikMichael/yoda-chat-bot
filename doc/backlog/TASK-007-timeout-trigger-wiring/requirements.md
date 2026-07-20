---
id: TASK-007
doc: requirements
updated: 2026-06-23
---

# TASK-007: timeout trigger wiring — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) delivers two compression triggers: an emergency **size** cutoff and a primary **timeout** path that compresses along semantic gaps during quiet periods. Upstream tasks landed pure trigger predicates and timeout window selection in `CompressionCore` ([[TASK-003-compression-window-algorithms-core/task|TASK-003]]), the `Maintenance` tick shell with dry-run predicate logging ([[TASK-004-maintenance-integration-shell/task|TASK-004]]), and the full snapshot → transform → graft+merge apply pipeline with **size-trigger-only** live wiring ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]). Today `Maintenance.compress_conversations` logs timeout predicate hits but never invokes apply for them.

This task wires the timeout trigger into the existing apply pipeline: when `CompressionCore.should_evaluate_timeout_trigger` is true, run the same apply steps as TASK-006 but with `CompressionCore.select_timeout_trigger_window` for step 1. No changes to transformation steps, `CompressionCore` algorithms, stash schema, or Chroma/recall.

Stakeholders: users in long-running chats (timely compression at natural quiet boundaries without waiting for the 300-message emergency), operators (debug audit of which trigger fired), and downstream tasks ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] drains summaries evicted by either trigger).

## Functional requirements

### FR-1: Timeout-trigger apply wiring in `Maintenance.compress_conversations`

Replace dry-run-only timeout handling with live apply on the same tick loop TASK-006 already uses.

**Acceptance criteria:**
- [ ] On each Maintenance tick, for each conversation from `MemoryProvider.iter_conversations()`: when `CompressionCore.should_evaluate_timeout_trigger(...)` is `True` and the size trigger did **not** invoke apply for that conversation on this tick, invoke the full compression apply pipeline for that conversation (FR-2–FR-4).
- [ ] When the timeout predicate is `False`, no timeout apply is attempted for that conversation on that tick.
- [ ] When **both** size and timeout predicates are `True` on the same tick for the same conversation, only the size-trigger apply runs on that tick (size is the emergency path; timeout may run on a later tick once quiet-and-changed predicates hold again).
- [ ] Successful timeout compression logs at **debug** with `chat_id` and `trigger=timeout`; no message text, summary body, or profile payloads at info level or above.
- [ ] Predicate evaluation continues to use `conversation.visible_messages`, `last_visible_at`, `last_compressed_at`, `now`, loaded `ChatCompressionSettings`, resolved `chat_type`, and `tick_seconds` (`maintenance_settings.tick_minutes * 60`) — no duplicate predicate logic in the Integration.

### FR-2: Timeout window selection at apply entry

Timeout runs use the gap-walk algorithm from TASK-003, not size halving and not a fallback between algorithms.

**Acceptance criteria:**
- [ ] On timeout-trigger apply, window selection calls `CompressionCore.select_timeout_trigger_window(snapshot.copy.messages, settings, chat_type, tick_seconds)` — never `select_size_trigger_window` and never falling back to halving when timeout selection returns `None`.
- [ ] When `select_timeout_trigger_window` returns `None`, the run aborts as a no-op: live conversation, profiles, `Chat.history`, and counters are unchanged; `last_compressed_at` is not updated; the tick continues with other conversations.
- [ ] Split semantics match TASK-006: messages `[0:split)` feed compressible-chunk construction; `[split:]` is the live tail retained raw before chunk shaping.
- [ ] `chat_type` is resolved via `MemoryProvider.get_chat_type(chat_id)` with the same fail-fast rules as existing maintenance wiring.

### FR-3: Reuse TASK-006 apply pipeline without modification

The timeout path shares the existing apply contract — snapshot, transform on copy, commit — rather than a parallel implementation.

**Acceptance criteria:**
- [ ] Timeout apply uses `MemoryProvider.take_compression_snapshot` and `MemoryProvider.commit_compression` with the same lock, graft+merge, `new_arrivals` reconciliation, and in-memory-only commit semantics as TASK-006 FR-1–FR-13.
- [ ] After timeout window selection, transformation steps match TASK-006: `CompressionApplyCore.slice_compressible_chunk` (skipping leading `prompt` and contiguous existing `summary` blocks), strip/refresh `user_introduction`, `SummarizerProvider.summarise`, profile deltas, inline `summary` insertion, FIFO eviction, derived-field updates, and `Chat.history` audit entry.
- [ ] Summariser failure, empty chunk after strip, or other TASK-006 no-op abort paths leave live state unchanged.
- [ ] `Maintenance` remains an Integration: it orchestrates Providers/Core calls and `await`; it does not embed window-selection or chunk-shaping business rules beyond choosing which `CompressionCore` selector to call.
- [ ] Refactoring to deduplicate size and timeout apply paths (e.g. one internal helper parameterized by trigger label and window selector) is allowed; observable behavior and IODA boundaries must match the above.

### FR-4: Variant C — existing inline summaries are never re-summarised

Per [[chat_context_management#Interaction between triggers]], every compression run (size or timeout) may add a new inline `summary` block but must **never** pass existing inline `summary` content to the summariser or replace/merge prior summary blocks (variant B is excluded). Timeout wiring must preserve this invariant on top of the TASK-006 apply pipeline.

**Acceptance criteria:**
- [ ] Leading `prompt` and contiguous existing `summary` blocks in the compressible region are skipped before summarisation per `CompressionApplyCore.slice_compressible_chunk` — only raw messages after the last retained summary boundary enter the summariser payload.
- [ ] After any successful timeout-trigger apply on a conversation that already has one or more inline `summary` blocks, every pre-existing summary's `Message.text` envelope is **byte-identical** to its value before the run.
- [ ] A successful timeout apply on such a conversation adds exactly one new `kind == "summary"` message; the new block's `summary_id` differs from every pre-existing summary's `summary_id`.
- [ ] Resulting `live.messages` order is `[prompt, …existing summary block(s) in chronological order…, new_summary, …live tail…]` — parallel summaries, not a combined rewrite.
- [ ] **Primary integration fixture** (canonical cross-trigger case from the master design): after a successful size-trigger apply, a later successful timeout-trigger apply on separate ticks yields at least two inline summaries with the properties above. The same properties hold when the pre-existing summary was produced by an earlier timeout run (timeout → timeout).

### FR-5: Quiet period with qualifying gap compresses; continuous traffic without gap is a no-op

Lock the two primary timeout behaviors called out in the task definition.

**Acceptance criteria:**
- [ ] **Happy path:** with a synthetic conversation where timeout predicates pass (`visible_messages` above entry guard, `last_visible_at` old enough for quiet-for-N-runs, `last_visible_at > last_compressed_at`) and message timestamps contain a visible-message gap strictly greater than `gap_threshold_seconds`, `compress_conversations` produces exactly one new inline `summary`, decrements `visible_messages` by the compressed chunk's visible count, and sets `last_compressed_at` to the snapshot timestamp.
- [ ] **No qualifying gap:** with predicates passing but all inter-visible gaps ≤ `gap_threshold_seconds` (continuously active burst history), `compress_conversations` performs no apply: no new `summary`, `SummarizerProvider.summarise` is not called, counters unchanged.
- [ ] **Predicate quiet check:** when `last_visible_at` is too recent for `is_quiet_for_n_runs`, no timeout apply runs even if the message list contains a large internal gap (quiet gate is evaluated before window selection).

### FR-6: Post-apply invariants and trigger logging

Timeout runs inherit TASK-006 success invariants and extend operational logging.

**Acceptance criteria:**
- [ ] After every successful timeout apply, the `user_introduction` post-apply invariant from TASK-006 FR-13 holds on `live.messages`.
- [ ] `Chat.history` receives a `compression` audit entry for timeout applies with the same envelope shape as size applies (TASK-006 FR-11).
- [ ] `test_timeout_no_apply_without_size_trigger` (or its successor) is updated: timeout-only conversations with qualifying fixtures **do** invoke apply and log `trigger=timeout`; size-only conversations still log `trigger=size`.
- [ ] `python -m pytest` from the project root passes with new and updated tests.

## Constraints & assumptions

- **Constraint (IODA):** Trigger predicates and timeout window selection stay in `CompressionCore`; apply transformation stays in `CompressionApplyCore` + `Maintenance` orchestration; `Maintenance` does not import LLM, embedding, or vector APIs.
- **Constraint (delivery profile):** Epic `internal_compat: none` — no acceptance criteria for partial deploy states between member tasks on the shared branch. Epic `external_contract: migrate-on-merge` — timeout apply uses counters and `last_compressed_at` from TASK-001 migration; no new stash schema version in this task.
- **Constraint (ADR-000):** Apply updates in-memory `Conversation` state only — no `save_conversation_stash` on apply or Maintenance tick.
- **Constraint:** Two algorithms, not one — timeout apply must never call `select_size_trigger_window`; size apply must never call `select_timeout_trigger_window`; neither algorithm falls back to the other when its window selection returns `None`.
- **Constraint:** Variant C — never re-summarise existing inline `summary` blocks (variant B is permanently excluded).
- **Constraint:** At most one successful compression apply per conversation per Maintenance tick (when both triggers qualify, size wins on that tick per FR-1).
- **Constraint:** Fail fast on missing `chat_type` and summariser validation errors — same as TASK-006.
- **Assumption:** [[TASK-003-compression-window-algorithms-core/task|TASK-003]] and [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] are complete: `CompressionCore` timeout predicates/windows and the size-trigger apply pipeline behave as specified.
- **Assumption:** `visible_messages`, `last_visible_at`, and `last_compressed_at` on each `Conversation` reflect live ingest and prior apply; maintenance does not recompute `visible_messages` from the message list except in tests.
- **Assumption:** Activity semantics for the quiet check are already encoded in `last_visible_at` bumps on visible (`user` or `assistant`) ingest per TASK-001; no separate activity counter is introduced.
- **Assumption:** `flush_summary_outbox` remains a no-op; outbox entries from timeout-trigger eviction accumulate in-memory like size-trigger runs.

## Out of scope

- Changes to the apply algorithm (snapshot/transform/merge steps, lock contract, audit schema) beyond wiring and deduplication ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] owns the pipeline).
- Changes to `CompressionCore` window or firing predicates ([[TASK-003-compression-window-algorithms-core/task|TASK-003]]).
- Chroma, embeddings, real `flush_summary_outbox`, outbox health warnings ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]).
- `recall_conversation` agent skill ([[TASK-009-recall-conversation-skill/task|TASK-009]]).
- New `Message` / `Conversation` stash schema versions or migration changes ([[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]).
- Re-summarising or merging existing inline summaries (variant B).
- Inline summary excess rebalance when `max_summary_count` is exceeded by more than one per tick ([[TASK-011-inline-summary-excess-rebalance/task|TASK-011]]).
- `save_conversation_stash` on apply, ingest, or Maintenance tick ([[ADR-000-sensitive-data-persistence]]).
