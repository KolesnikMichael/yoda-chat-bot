---
id: TASK-003
doc: requirements
updated: 2026-06-15
---

# TASK-003: compression window algorithms core — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) needs pure, testable logic to decide **when** compression should run and **where** to split a conversation — before any LLM call, Redis lock, or apply pipeline exists. [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] landed `Message.kind`, conversation trigger bookkeeping (`visible_messages`, `last_visible_at`, `last_compressed_at`), and `ChatCompressionSettings` loaded at startup; nothing yet consumes those settings for compression.

This task delivers `CompressionCore` (IODA Core): sync static methods for visibility helpers, `GAP_THRESHOLD` derivation, the universal boundary-alignment rule, size-trigger window selection (halve + align), timeout-trigger window selection (gap walk with explicit no-op when no gap qualifies), and the trigger **firing predicates** themselves. Downstream tasks call this Core from the `Maintenance` Integration without re-embedding business rules: [[TASK-004-maintenance-integration-shell/task|TASK-004]] dry-run logging, [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] size-trigger apply, [[TASK-007-timeout-trigger-wiring/task|TASK-007]] timeout wiring.

Stakeholders: implementers of maintenance and apply (need stable, deterministic contracts), and operators (behavior must match the master design's two-trigger model — emergency halve vs semantic gap compression).

## Functional requirements

### FR-1: `CompressionCore` as pure Core logic

The compression window and trigger-decision algorithms live in one IODA Core class with no side effects.

**Acceptance criteria:**
- [ ] A `CompressionCore` class exists under `yoda/mind/` (exact module path is a design choice) exposing **only** `@staticmethod` methods.
- [ ] Methods are synchronous and perform no I/O, locking, LLM calls, logging of user content, or mutation of inputs (messages lists and settings are read-only; callers pass copies when mutation matters).
- [ ] The class depends only on Data types (`Message`, `MessageKind`, `ChatCompressionSettings`, and plain scalars/collections passed as parameters) — no imports from Integrations, Providers, Portals, or APIs.
- [ ] No wiring in `yoda_chat_bot.py`, `Maintenance`, or `MemoryProvider` is added in this task.

### FR-2: Visibility helper

Compression algorithms share a single definition of which messages count as visible, aligned with [[chat_context_management#Visibility]] and TASK-001's `VISIBLE_KINDS`.

**Acceptance criteria:**
- [ ] `CompressionCore` exposes a predicate (e.g. `is_visible(message) -> bool`) that returns `True` iff `message.kind` is `"user"` or `"assistant"`.
- [ ] All window-selection and gap-detection logic in this task uses that predicate — no duplicated kind checks inline.
- [ ] Non-visible kinds (`prompt`, `summary`, `task_result`, `user_introduction`) are treated as invisible for visible-message counting and gap measurement.

### FR-3: `GAP_THRESHOLD` derivation

Gap detection for the timeout-trigger uses a threshold derived from compression settings and chat type, per [[chat_context_management#Constants and entry threshold]].

**Acceptance criteria:**
- [ ] `CompressionCore` exposes a method (e.g. `gap_threshold_seconds(settings, chat_type, tick_seconds) -> float`) that computes  
  `quiet_runs_before_compression[chat_type] * gap_to_trigger_ratio * tick_seconds`,  
  where `chat_type` resolves to the `private` or `group` sub-key of `settings.quiet_runs_before_compression`.
- [ ] With repo defaults (`private=8`, `group=8`, `gap_to_trigger_ratio=0.5`, `tick_seconds=3600`), the method returns `14400.0` (4 hours in seconds).
- [ ] Changing only the group quiet-runs value changes the group threshold proportionally; private and group thresholds are independent.
- [ ] Invalid or unknown `chat_type` values fail fast (`ValueError` or equivalent) — no silent default to private.

### FR-4: Universal boundary alignment

Every candidate split index is adjusted so the live tail starts on a `user` message (private and group chats alike), per [[chat_context_management#Boundary alignment by kind (universal rule)]]. `user_introduction` markers in the compressed chunk are restored on apply (TASK-006 step 8), not by alignment.

**Acceptance criteria:**
- [ ] `CompressionCore` exposes boundary alignment (e.g. `align_boundary(messages, split_index) -> int`) that takes a candidate index into `messages` (first message of the live tail) and returns an adjusted index **≥** the candidate, never moving the boundary earlier into the would-be compressed region.
- [ ] The returned index points at a message with `kind == "user"`, or at `len(messages)` if no `user` message exists from the candidate through the end of the list.
- [ ] When the message at the candidate index is already `kind == "user"`, alignment is a no-op (same index returned).
- [ ] Size-trigger window selection always applies alignment after halving; timeout-trigger window selection applies alignment after gap placement (typically shifting `assistant` forward to the next `user`).
- [ ] Unit tests cover at least: halve landing on `assistant` shifted forward to next `user`; group chat with a long tail containing no forward `user_introduction` still aligns on the next `user` message (compression not blocked).

### FR-5: Size-trigger window selection

Emergency cutoff selects the older half of visible traffic, then aligns, per [[chat_context_management#Size-trigger — emergency cutoff]].

**Acceptance criteria:**
- [ ] `CompressionCore` exposes size-trigger window selection (e.g. `select_size_trigger_window(messages) -> int | None`) returning the split index: messages `[0:split)` are the compression chunk boundary input, `[split:]` is the live tail.
- [ ] Selection uses **visible-message count only** (ignores `prompt`, `summary`, `task_result`, `user_introduction` for the halving arithmetic).
- [ ] The older half of visible messages is designated for compression and the newer half retained raw before alignment (exact index arithmetic is a design detail; tests must fix behavior on fixtures with interleaved non-visible messages).
- [ ] Boundary alignment (FR-4) is applied to the halving result.
- [ ] If alignment yields no valid tail start (index `len(messages)` with an empty tail) or a zero-width compressible region, the method returns `None` (no-op) rather than an invalid split — exact edge-case rule is a design choice but must be deterministic and tested.

### FR-6: Timeout-trigger window selection

Primary compression path walks backward for a qualifying gap, per [[chat_context_management#Window selection algorithm]].

**Acceptance criteria:**
- [ ] `CompressionCore` exposes timeout-trigger window selection (e.g. `select_timeout_trigger_window(messages, settings, chat_type, tick_seconds) -> int | None`) returning a split index with the same `[0:split)` / `[split:]` semantics as FR-5, or `None` when the run must abort as a no-op.
- [ ] Algorithm walks backward from the newest message, counting only visible messages, until at least `settings.min_chunk_length` visible messages have been seen in the tail candidate.
- [ ] It then continues backward seeking the first **gap**: elapsed time between two consecutive visible messages (by parsed timestamps) **strictly greater than** `gap_threshold_seconds` from FR-3.
- [ ] Gap intervals are measured between visible messages only; non-visible messages between visible ones do not create gaps.
- [ ] When a gap is found, the split is placed so non-visible messages falling inside the gap belong to the live tail (not the chunk) — they attach to the next burst per master design step 6.
- [ ] If no qualifying gap exists in the searched range, the method returns `None` — **no** fallback to size-trigger halving.
- [ ] After gap placement, boundary alignment (FR-4) is applied.
- [ ] The live tail retains **at least** `min_chunk_length` visible messages (may retain more when walking back through same-burst visible traffic).
- [ ] Timestamp parsing for gap duration uses epoch seconds consistent with `MemoryCore.parse_message_timestamp` on the same string inputs (shared helper extraction vs duplicate implementation is a design choice).
- [ ] Unit tests include: clear gap → non-`None` split; continuously active visible traffic with all inter-message gaps ≤ threshold → `None`; `task_result` sandwiched between visible messages without splitting the burst.

### FR-7: Size-trigger firing predicate

**Acceptance criteria:**
- [ ] `CompressionCore` exposes a pure predicate (e.g. `should_fire_size_trigger(visible_messages, settings) -> bool`) that returns `True` iff `visible_messages > settings.size_trigger_threshold`.
- [ ] With default threshold `300`, `visible_messages == 300` is `False` and `301` is `True`.

### FR-8: Timeout-trigger firing predicates

Three checks gate timeout-trigger evaluation, per [[chat_context_management#Timeout-trigger — clean-chunk compression]] and the entry threshold note.

**Acceptance criteria:**
- [ ] **Entry guard:** a predicate (e.g. `passes_timeout_entry_guard(visible_messages, settings) -> bool`) returns `True` iff `visible_messages > 2 * settings.min_chunk_length` (strict inequality). With default `min_chunk_length=30`, `visible_messages == 60` is `False` and `61` is `True`.
- [ ] **Quiet-for-N-runs:** a predicate (e.g. `is_quiet_for_n_runs(last_visible_at, now, settings, chat_type, tick_seconds) -> bool`) returns `True` iff `now - last_visible_at >= quiet_runs_before_compression[chat_type] * tick_seconds` (using the same `chat_type` key resolution and fail-fast rules as FR-3).
- [ ] **Changed since last compression:** a predicate (e.g. `has_visible_activity_since_compression(last_visible_at, last_compressed_at) -> bool`) returns `True` iff `last_visible_at > last_compressed_at`.
- [ ] With defaults `last_compressed_at=0.0` and any positive `last_visible_at`, the changed-since predicate is `True` (matches migration defaults for never-compressed conversations).
- [ ] A composite helper (e.g. `should_evaluate_timeout_trigger(...) -> bool`) may combine entry guard + quiet + changed checks; if provided, it returns the logical AND of the three predicates.

### FR-9: Unit tests on synthetic fixtures

Behavior is locked by deterministic tests without Redis, LLM, or maintenance wiring.

**Acceptance criteria:**
- [ ] Tests live under `tests/` and construct synthetic `Message` lists with explicit `kind`, `timestamp`, and optional `user_id`.
- [ ] Coverage includes FR-2 through FR-8: visibility, `gap_threshold_seconds` defaults and chat-type split, boundary alignment on `user`, size window halving + alignment, timeout window gap / no-gap / no fallback, all firing predicates including boundary values at thresholds.
- [ ] Tests run with `python -m pytest` from the project root and pass alongside the existing suite.

## Constraints & assumptions

- **Constraint:** Follow IODA — all logic in `CompressionCore` (Core); callers in later tasks pass `Conversation` fields and `messages` as parameters; Integrations must not duplicate predicate or window rules.
- **Constraint:** Two algorithms, not one — size-trigger halving must never be invoked as a fallback when timeout gap detection fails.
- **Constraint:** `chat_type` strings are `"private"` and `"group"`, matching `Chat.chat_type` and `QuietRunsSettings` keys from TASK-001.
- **Constraint:** `tick_seconds` is supplied by callers (from `mind.maintenance.tick_minutes` in later tasks); this task does not load maintenance settings.
- **Constraint:** Window selection returns a split index or `None` only — no summarisation, snapshot, lock, graft/merge, `user_introduction` strip/refresh, or counter mutation (`visible_messages`, `last_compressed_at`).
- **Assumption:** [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] is complete: `Message.kind`, conversation counters, and `ChatCompressionSettings` exist as specified.
- **Assumption:** `visible_messages` passed into firing predicates reflects live conversation state maintained by ingest and (later) apply; this task does not recompute the counter from the message list except in tests.
- **Assumption:** Activity semantics for timeout ("user messages only" in the master design narrative) are already reflected in `last_visible_at` bumping on visible (`user` **or** `assistant`) ingest per TASK-001; firing predicates use `last_visible_at` as the quiet check input without a separate activity counter.
- **Assumption:** Skipping leading `prompt` and existing `summary` blocks when building the summariser payload is owned by compression apply ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]), not window selection — FR-5/FR-6 define the split boundary only.
- **Assumption:** `user_introduction` messages that land in the compressed chunk are stripped and refreshed on apply ([[chat_context_management#Refresh during compression]]); alignment does not keep them in the live tail.

## Out of scope

- LLM summarisation, `SummarizerProvider`, profile extraction ([[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]).
- Snapshot, per-conversation lock, apply, graft+merge, counter updates on successful compression ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]).
- `Maintenance` integration, periodic tick loop, dry-run or live wiring ([[TASK-004-maintenance-integration-shell/task|TASK-004]], [[TASK-007-timeout-trigger-wiring/task|TASK-007]]).
- `user_introduction` strip/refresh during compression ([[TASK-002-user-introduction-on-ingest/task|TASK-002]], TASK-006).
- Chroma, embeddings, summary outbox, `recall_conversation` ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]], [[TASK-009-recall-conversation-skill/task|TASK-009]]).
- Loading `ChatCompressionSettings` or maintenance settings from `settings.json` (TASK-001 / TASK-004 respectively) — callers pass already-loaded settings and `tick_seconds`.
- Changes to `Message`, `Conversation`, stash migration, or ingest counter behavior (TASK-001).
