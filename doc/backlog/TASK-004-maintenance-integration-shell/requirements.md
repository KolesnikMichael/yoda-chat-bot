---
id: TASK-004
doc: requirements
updated: 2026-06-15
---

# TASK-004: maintenance integration shell — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) needs a dedicated home for periodic background work — compression triggers, summary outbox flush, and scheduler metadata reconciliation — instead of ad-hoc closures in `yoda_chat_bot.py`. [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] landed conversation trigger bookkeeping and `ChatCompressionSettings`; [[TASK-003-compression-window-algorithms-core/task|TASK-003]] landed `CompressionCore` firing predicates and window selection. Nothing yet runs those predicates on live conversations on a schedule.

This task introduces the `Maintenance` Integration (IODA Integration — orchestration only): a single periodic tick loop, relocation of `reconcile_active_jobs` from the wiring file, lifecycle hooks (`run_initial_pass`, `start`, `stop`), and **stubs** for `compress_conversations` (dry-run: evaluate and log trigger candidates via `CompressionCore` predicates, no apply) and `flush_summary_outbox` (no-op). The shell prepares the seam for real compression apply in [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] and outbox flush in [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]].

Stakeholders: operators (predictable periodic behavior, preserved daily job reconciliation), and implementers of downstream apply/flush tasks (stable Maintenance API and tick semantics).

## Functional requirements

### FR-1: `Maintenance` Integration class

Periodic background orchestration lives in one IODA Integration with no embedded compression business rules.

**Acceptance criteria:**
- [ ] A `Maintenance` class exists under `yoda/mind/` (exact module path is a design choice) and is constructed in `yoda_chat_bot.py:main()` like other Integrations (`Mind`, `Perception`).
- [ ] The class depends on injected Operations/APIs only — at minimum `StorageApi`, `SchedulerApi`, `MemoryProvider`, `ChatCompressionSettings`, and maintenance tick settings (FR-2) for this task; it does **not** import or call `CompressionCore` logic inline beyond delegating to `CompressionCore` static methods.
- [ ] Trigger firing decisions use `CompressionCore` predicates (`should_fire_size_trigger`, `should_evaluate_timeout_trigger`, and related helpers) — no duplicated threshold or quiet-period rules in `Maintenance`.
- [ ] `Maintenance` performs no compression apply, summarisation, embedding, Chroma I/O, or conversation message mutation in this task.

### FR-2: Maintenance settings loaded at startup

The Maintenance loop period is configured explicitly, separate from compression constants.

**Acceptance criteria:**
- [ ] A Data type (e.g. `MaintenanceSettings`) exposes `tick_minutes: int` loaded from `settings.json → mind.maintenance.tick_minutes`.
- [ ] Repo default `tick_minutes` is `60`, matching [[chat_context_management#Single ticking loop]].
- [ ] Startup loading fails fast (`ValueError` or equivalent) if the `mind.maintenance` block or `tick_minutes` is missing — no silent fallback.
- [ ] `Maintenance` receives `tick_seconds` derived as `tick_minutes * 60` (float) when calling `CompressionCore` timeout-related predicates.
- [ ] `ChatCompressionSettings` (already loaded in `yoda_chat_bot.py` from TASK-001) is passed into `Maintenance` for dry-run predicate evaluation.

### FR-3: Single periodic tick loop

One asyncio task drives all Maintenance sub-routines at harmonised periods, per [[chat_context_management#Single ticking loop]].

**Acceptance criteria:**
- [ ] `Maintenance.start()` installs **one** background asyncio task (not one task per sub-routine).
- [ ] The loop sleeps `tick_minutes * 60` seconds between ticks (same base period for all sub-routines in this task).
- [ ] On each tick, in order: `compress_conversations` (FR-6), then `flush_summary_outbox` (FR-7); `reconcile_active_jobs` (FR-5) runs when the tick counter is divisible by `24` (≈ daily when `tick_minutes=60`, preserving today's behaviour).
- [ ] Sub-routine periods are integer multiples of the base tick (`1` tick for compression and outbox stub, `24` ticks for reconciliation).
- [ ] An exception in one sub-routine is caught and logged; the loop continues on subsequent ticks (same resilience as today's `periodic_job_cleanup`).
- [ ] `Maintenance.stop()` cancels the loop task and awaits it, swallowing `asyncio.CancelledError` as appropriate so shutdown completes cleanly.

### FR-4: Lifecycle API wired in `yoda_chat_bot.py`

The wiring file owns construction and startup/shutdown hooks; Maintenance owns periodic behaviour.

**Acceptance criteria:**
- [ ] `Maintenance` exposes `async def run_initial_pass() -> None` — performs one-shot startup work currently done inline in `on_app_start` (initial `reconcile_active_jobs`).
- [ ] `Maintenance` exposes `def start() -> None` (or `async def start()` if the design requires it) — starts the periodic loop after `run_initial_pass`.
- [ ] `Maintenance` exposes `async def stop() -> None` — stops the periodic loop; called from `on_post_stop`.
- [ ] `on_app_start` calls `await maintenance.run_initial_pass()` then `maintenance.start()` in place of the inline `reconcile_active_jobs` call and `asyncio.create_task(periodic_job_cleanup())`.
- [ ] `on_post_stop` calls `await maintenance.stop()` in place of the `periodic_cleanup_holder` cancel/await block.
- [ ] `cleanup_job_metadata` (the per-job scheduler callback) **remains** in `yoda_chat_bot.py` — not moved into `Maintenance`.

### FR-5: `reconcile_active_jobs` relocated from wiring file

Scheduler metadata reconciliation keeps today's semantics but lives with Maintenance.

**Acceptance criteria:**
- [ ] `reconcile_active_jobs` is no longer defined in `yoda/yoda_chat_bot.py`.
- [ ] Behaviour is unchanged: scan Redis `active_jobs:*` hashes, remove entries whose job id is absent from `scheduler_api.get_job_ids()`, log an info line when any entries were removed, return the removal count.
- [ ] Initial reconciliation still runs once at startup via `run_initial_pass()`; periodic reconciliation still runs ≈ daily via the tick loop (FR-3).
- [ ] Existing tests in `tests/test_agent_tools.py` (or equivalent) import `reconcile_active_jobs` from its new location and continue to pass.

### FR-6: `compress_conversations` dry-run stub

Each tick evaluates compression trigger candidates on loaded conversations without applying compression.

**Acceptance criteria:**
- [ ] `compress_conversations` runs on every Maintenance tick (FR-3).
- [ ] It iterates all in-memory conversations held by `MemoryProvider` (a Provider accessor for iteration is added if none exists — design choice).
- [ ] For each conversation, `chat_type` (`"private"` or `"group"`) is resolved for timeout evaluation (from persisted chat metadata via `StorageApi` or a `MemoryProvider` helper — design choice); unknown or missing `chat_type` fails fast rather than defaulting silently.
- [ ] For each conversation, `CompressionCore.should_fire_size_trigger(visible_messages, settings)` is evaluated using the conversation's `visible_messages` counter and loaded `ChatCompressionSettings`.
- [ ] For each conversation, `CompressionCore.should_evaluate_timeout_trigger(...)` is evaluated using `visible_messages`, `last_visible_at`, `last_compressed_at`, current time (`now`), `ChatCompressionSettings`, resolved `chat_type`, and `tick_seconds`.
- [ ] When either predicate is `True`, `Maintenance` logs at **debug** level a candidate record containing at least `chat_id` and which trigger(s) fired (`size`, `timeout`, or both) — no message text, profile content, or summary payloads in logs.
- [ ] Dry-run performs **no** window selection, locking, LLM calls, stash writes, counter updates (`visible_messages`, `last_compressed_at`), or `pending_vectorization` changes — predicate evaluation and logging only.
- [ ] Conversations where both predicates are `False` produce no dry-run log line for that conversation on that tick.

### FR-7: `flush_summary_outbox` stub

The outbox flush sub-routine exists as a callable seam but does nothing until TASK-008.

**Acceptance criteria:**
- [ ] `flush_summary_outbox` is invoked on every Maintenance tick (FR-3), independent of compression.
- [ ] The stub is a no-op: it does not read or mutate `Conversation.pending_vectorization`, does not call embedding or vector APIs, and does not log outbox health warnings.
- [ ] The method exists as an awaitable sub-routine callable from the tick loop so TASK-008 can replace the body without changing loop structure.

### FR-8: Wiring file cleanup

Ad-hoc periodic cleanup code is removed from `yoda_chat_bot.py`.

**Acceptance criteria:**
- [ ] The module-level `reconcile_active_jobs` function is removed from `yoda/yoda_chat_bot.py`.
- [ ] The `periodic_job_cleanup` closure and `periodic_cleanup_holder` dict are removed from `yoda/yoda_chat_bot.py`.
- [ ] No `asyncio.create_task(periodic_job_cleanup())` remains in the wiring file.
- [ ] `python -m pytest` from the project root passes with the relocated reconciliation and new Maintenance wiring.

## Constraints & assumptions

- **Constraint:** Follow IODA — `Maintenance` is an Integration (orchestration + await only); trigger predicates and window rules stay in `CompressionCore` (Core); settings are Data types loaded in the wiring file.
- **Constraint:** Epic `internal_compat` is `none` — member tasks land together on the shared branch; no acceptance criteria defend partial deploy states between TASK-004 and sibling tasks.
- **Constraint:** Epic `external_contract` is `migrate-on-merge` — this task does not change conversation stash schema or migration; no new Redis migration requirements.
- **Constraint:** `tick_seconds` passed to `CompressionCore` must match the Maintenance loop's base period (`tick_minutes * 60`).
- **Constraint:** `logger.debug` for dry-run candidate logs (may include `chat_id`); no user message or profile content at info level or above.
- **Assumption:** [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] and [[TASK-003-compression-window-algorithms-core/task|TASK-003]] are complete: `Message.kind`, conversation counters, `ChatCompressionSettings`, and `CompressionCore` predicates exist as specified.
- **Assumption:** `visible_messages`, `last_visible_at`, and `last_compressed_at` on each `Conversation` reflect live ingest state; dry-run does not recompute counters from the message list.
- **Assumption:** `SummarizerProvider`, `EmbeddingProvider`, and `VectorProvider` do not exist yet; `Maintenance` is constructed with only the dependencies this shell needs. Later tasks extend the constructor/wiring per master design without changing FR-3 tick structure.
- **Assumption:** Dry-run logs **both** size and timeout predicate hits even though [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] will wire only size-trigger apply first; timeout apply follows in [[TASK-007-timeout-trigger-wiring/task|TASK-007]].

## Out of scope

- Compression apply pipeline: snapshot, lock, summariser call, graft+merge, `summary` messages, counter updates ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]).
- Timeout-trigger apply wiring beyond dry-run predicate logging ([[TASK-007-timeout-trigger-wiring/task|TASK-007]]).
- `SummarizerProvider` and profile extraction ([[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]).
- Real `flush_summary_outbox` (embeddings, Chroma, outbox health warnings) ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]]).
- `recall_conversation` skill ([[TASK-009-recall-conversation-skill/task|TASK-009]]).
- Changes to `CompressionCore` algorithms, `Message` / `Conversation` schema, or stash migration.
- Moving `cleanup_job_metadata` out of `yoda_chat_bot.py`.
- Per-conversation `asyncio.Lock` for compression ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]).
