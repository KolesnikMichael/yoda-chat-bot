---
id: TASK-007
doc: design
updated: 2026-06-22
---

# TASK-007: timeout trigger wiring — Design

← [[task|Back to task]] | [[requirements|Requirements]]

## Solution overview

Wire the timeout trigger into `Maintenance.compress_conversations` by reusing the TASK-006 apply pipeline with a different window selector: when `CompressionCore.should_evaluate_timeout_trigger` is true and the size predicate did not claim the tick (`elif`, not a second pass), run the same snapshot → transform → commit sequence as size apply but call `CompressionCore.select_timeout_trigger_window` instead of `select_size_trigger_window`. Refactor the duplicated orchestration into one internal `_run_compression_apply` helper parameterized by trigger label and split selector so variant C (parallel inline summaries, never re-summarise) and all TASK-006 abort paths inherit unchanged from `CompressionApplyCore`. No changes to Core algorithms, apply transformation, stash schema, or persistence.

## Architecture

```mermaid
sequenceDiagram
    participant M as Maintenance
    participant CC as CompressionCore
    participant MP as MemoryProvider
    participant CAC as CompressionApplyCore
    participant SP as SummarizerProvider

    M->>M: compress_conversations (per conversation)
    M->>MP: get_chat_type(chat_id)
    M->>CC: should_fire_size_trigger / should_evaluate_timeout_trigger
    alt size predicate true
        M->>M: _run_compression_apply(trigger=size)
    else timeout predicate true (size predicate false)
        M->>M: _run_compression_apply(trigger=timeout)
    end
    M->>MP: take_compression_snapshot(chat_id)
    alt trigger == size
        M->>CC: select_size_trigger_window(messages)
    else trigger == timeout
        M->>CC: select_timeout_trigger_window(messages, settings, chat_type, tick_seconds)
    end
    Note over M,CC: None → no-op abort; no cross-algorithm fallback
    M->>CAC: slice_compressible_chunk → strip → summarise → graft steps
    M->>SP: summarise (outside lock)
    M->>MP: commit_compression
    M->>M: logger.debug(trigger=size|timeout)
```

| Component | IODA | Role in this task |
|-----------|------|-------------------|
| `Maintenance.compress_conversations` | Integration | Evaluate predicates; size-first `if` / timeout `elif`; delegate apply |
| `Maintenance._run_compression_apply` | Integration | Shared orchestration (extracted from `_run_size_trigger_compression`) |
| `CompressionCore` | Core | Unchanged — timeout predicates + `select_timeout_trigger_window` ([[TASK-003-compression-window-algorithms-core/task\|TASK-003]]) |
| `CompressionApplyCore` | Core | Unchanged — variant C via `slice_compressible_chunk` ([[TASK-006-compression-apply-and-size-trigger/task\|TASK-006]]) |
| `MemoryProvider` | Provider | Unchanged snapshot/commit/lock contract |
| `SummarizerProvider` | Provider | Unchanged |

Cross-cutting trigger interaction and variant C: [[chat_context_management#Interaction between triggers]]. Timeout window algorithm: [[chat_context_management#Timeout-trigger — clean-chunk compression]].

## Key decisions

### Decision 1: Single shared apply helper

**Context:** FR-3 permits deduplication; `_run_size_trigger_compression` and a timeout path differ only in window selection and debug log label.
**Options:** (A) Copy-paste `_run_timeout_trigger_compression` as a second ~130-line method; (B) extract `_run_compression_apply(conversation, trigger, chat_type)` with a trigger-specific split call at the top.
**Choice:** B — one helper, two thin call sites (`_run_size_trigger_compression` / `_run_timeout_trigger_compression` may remain as one-liner wrappers or be inlined). Observable behaviour and IODA boundaries unchanged. (FR-3)

### Decision 2: Size predicate blocks timeout on the same tick

**Context:** FR-1 requires at most one apply per conversation per tick; when both predicates are true, size wins.
**Options:** (A) `if size_predicate: size_apply` then `if timeout_predicate and not size_committed: timeout_apply`; (B) `if size_predicate: size_apply elif timeout_predicate: timeout_apply`.
**Choice:** B — timeout does not run on a tick where the size **predicate** is true, even if size apply aborts as a no-op (window `None`, empty chunk, summariser failure). Timeout may run on a later tick once `should_fire_size_trigger` is false and quiet/changed predicates still hold. Matches master design emergency-vs-primary split. (FR-1)

### Decision 3: No algorithm crossover on `None`

**Context:** FR-2 and constraints forbid halving fallback when timeout window selection returns `None`.
**Options:** (A) Fall back to `select_size_trigger_window` when timeout returns `None`; (B) abort no-op and continue tick.
**Choice:** B — identical to existing size-path behaviour when its selector returns `None`. (FR-2, FR-5)

### Decision 4: Variant C is inherited, not reimplemented

**Context:** FR-4 requires parallel summaries without re-summarising existing blocks.
**Options:** (A) Timeout-specific chunk logic in `Maintenance`; (B) rely on `CompressionApplyCore.slice_compressible_chunk` skipping leading `prompt` + contiguous `summary` blocks.
**Choice:** B — no `CompressionApplyCore` changes; timeout wiring only supplies a gap-based `split`. Tests prove byte-identical prior summaries and one new `summary_id`. (FR-4)

### Decision 5: Preserve TASK-004 candidate logging

**Context:** Existing `compress_conversations` logs `compression trigger candidate` with both triggers before apply.
**Options:** (A) Remove candidate log when apply runs; (B) keep candidate log, add `compression applied: … trigger=timeout|size` on success.
**Choice:** B — operators retain predicate audit; success log carries the trigger that committed. (FR-1, FR-6)

## Interfaces

### `Maintenance.compress_conversations` (updated control flow)

```python
async def compress_conversations(self) -> None:
    now = time.time()
    for conversation in self._memory_provider.iter_conversations():
        chat_type = await self._memory_provider.get_chat_type(conversation.chat_id)
        triggers: list[str] = []
        if CompressionCore.should_fire_size_trigger(
            conversation.visible_messages, self._compression_settings
        ):
            triggers.append("size")
        if CompressionCore.should_evaluate_timeout_trigger(
            conversation.visible_messages,
            conversation.last_visible_at,
            conversation.last_compressed_at,
            now,
            self._compression_settings,
            chat_type,
            self._tick_seconds,
        ):
            triggers.append("timeout")
        if triggers:
            logger.debug(
                "compression trigger candidate: chat_id=%s triggers=%s",
                conversation.chat_id,
                triggers,
            )
        if "size" in triggers:
            await self._run_compression_apply(conversation, "size", chat_type)
        elif "timeout" in triggers:
            await self._run_compression_apply(conversation, "timeout", chat_type)
```

Predicate arguments unchanged from TASK-004/TASK-006; no duplicate predicate logic in the Integration (FR-1).

### `Maintenance._run_compression_apply` (new; replaces body of `_run_size_trigger_compression`)

```python
async def _run_compression_apply(
    self,
    conversation: Conversation,
    trigger: Literal["size", "timeout"],
    chat_type: str,
) -> None:
    chat_id = conversation.chat_id
    snapshot = await self._memory_provider.take_compression_snapshot(chat_id)
    if snapshot is None:
        return

    if trigger == "size":
        split = CompressionCore.select_size_trigger_window(snapshot.copy.messages)
    else:
        split = CompressionCore.select_timeout_trigger_window(
            snapshot.copy.messages,
            self._compression_settings,
            chat_type,
            self._tick_seconds,
        )
    if split is None:
        return

    # … remainder identical to current _run_size_trigger_compression
    # (slice_compressible_chunk through commit_compression) …

    logger.debug("compression applied: chat_id=%s trigger=%s", chat_id, trigger)
```

Steps 2–10 after window selection match TASK-006 `_run_size_trigger_compression` exactly: `slice_compressible_chunk`, strip/refresh, `SummarizerProvider.summarise`, profile deltas, inline summary, FIFO eviction, derived fields, audit entry, `commit_compression`. Summariser failure and empty-chunk aborts leave live state unchanged (FR-3).

### Window selection contracts (unchanged from TASK-003)

| Trigger | Method | Inputs | `None` meaning |
|---------|--------|--------|----------------|
| size | `CompressionCore.select_size_trigger_window` | `messages` | No valid halved boundary |
| timeout | `CompressionCore.select_timeout_trigger_window` | `messages`, `settings`, `chat_type`, `tick_seconds` | No qualifying visible gap ≥ `gap_threshold_seconds` with min tail length |

`chat_type` resolved via `MemoryProvider.get_chat_type` — fail-fast on unknown values, same as existing maintenance wiring (FR-2).

### Test fixtures (`tests/test_compression_apply.py`)

| Helper | Purpose | Key properties |
|--------|---------|----------------|
| `timeout_only_compression_settings()` | Isolate timeout `elif` branch | `size_trigger_threshold=300` — with `low_compression_settings()` (`threshold=4`), any conversation that passes the timeout predicate also passes size; timeout-only tests must elevate the size threshold |
| `build_timeout_compressible_conversation` | FR-5 happy path | `_ts(hours)` spacing; one inter-visible gap > `gap_threshold_seconds` (`tick_minutes=1` → `gap_threshold=240s`); `last_compressed_at=0`, `last_visible_at` from tail message |
| `build_continuous_burst_conversation` | FR-5 no-gap no-op | `_ts_seconds()` with ≤30s inter-visible spacing — hourly `_ts()` gaps exceed threshold and falsely trigger compression |
| `build_quiet_but_internal_gap_conversation` | FR-5 quiet gate | Wraps timeout fixture; sets `last_visible_at` to `_ts(10.0)` (too recent for quiet-for-N-runs) |
| Cross-trigger integration (`tests/test_maintenance.py`) | FR-4 | Patch `time.time()` on **every** apply tick; set `last_compressed_at` explicitly before follow-up ticks — `has_visible_activity_since_compression` compares message timestamps against snapshot `time.time()`, so mixing January `build_compressible_conversation` dates with unpatched clock blocks tick-2 timeout |

Reuse `FakeSummarizerProvider` and `patch("yoda.mind.maintenance.time.time", …)` from existing maintenance tests. Size-path tests continue using `low_compression_settings()` / `default_compression_settings()`.

## System impact

| Path / class | IODA | Change | FR |
|--------------|------|--------|-----|
| `yoda/mind/maintenance.py` — `Maintenance.compress_conversations` | Integration | **Edit** — `elif` timeout branch calling shared apply | FR-1, FR-6 |
| `yoda/mind/maintenance.py` — `Maintenance._run_compression_apply` | Integration | **Create** — extract from `_run_size_trigger_compression`; parameterize trigger + window selector | FR-2, FR-3 |
| `yoda/mind/maintenance.py` — `Maintenance._run_size_trigger_compression` | Integration | **Deleted** — superseded by `_run_compression_apply` | FR-3 |
| `tests/test_maintenance.py` | Test | **Edit** — `test_timeout_apply_on_predicate`, FR-4 cross-trigger tests, both-triggers-same-tick, quiet/burst no-ops | FR-4, FR-5, FR-6 |
| `tests/test_compression_apply.py` | Test | **Edit** — `timeout_only_compression_settings`, timeout/burst/quiet fixture builders, size-path tests via `_run_compression_apply` | FR-3, FR-5 |

No changes to `CompressionCore`, `CompressionApplyCore`, `MemoryProvider`, `SummarizerProvider`, data models, or `settings.json`.

## Decisions made (from requirements review)

| Item | Resolution |
|------|------------|
| Size predicate true but size apply no-ops — run timeout same tick? | No — `elif` precedence; size predicate claims the tick (Decision 2) |
| Deduplicate apply paths? | Yes — `_run_compression_apply` (Decision 1; FR-3 explicitly allows) |
| Re-fetch `chat_type` inside apply helper? | Pass from `compress_conversations` to avoid duplicate `get_chat_type` per conversation per tick |

## Open questions

None.
