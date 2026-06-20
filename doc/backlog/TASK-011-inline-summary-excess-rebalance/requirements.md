---
id: TASK-011
doc: requirements
updated: 2026-06-18
---

# TASK-011: inline summary excess rebalance — Requirements

← [[task|Back to task]]

## Context

[[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] implements FIFO eviction with `to_evict = min(excess, summaries_added)` and `summaries_added=1` on every successful size-trigger apply. In the **steady state** (exactly `max` inline summaries), each apply adds one summary and evicts one → count stays at `max`. In **excess** (count > `max`, e.g. operator lowered `max_summary_count`, migration artefact, or bad state), each successful apply still adds one and evicts at most one → **net zero**; excess persists until manual intervention.

Rebalance is not required for the TASK-006 milestone (normal chats stay at `max`). This task addresses the anomalous excess path before production tuning of `max_summary_count` or if excess is observed in the wild.

Stakeholders: operators (predictable inline summary bound), downstream [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] (outbox depth).

## Problem statement

| State | After one successful apply (`summaries_added=1`) |
|-------|--------------------------------------------------|
| `count == max` | `count` unchanged ✓ |
| `count == max + k`, k ≥ 1 | `count` unchanged ✗ (stuck) |

Abort paths (no chunk, summariser failure) do **not** evict — excess cannot be drained by “idle” compression runs.

## Solution alternatives

Choose **one** at design time; document the rejected option in [[design]].

### Alternative A: Raise per-apply eviction cap (`summaries_added=2`)

Pass `summaries_added=2` (or `min(2, excess)` semantics) from `Maintenance._run_size_trigger_compression`. When `excess ≥ 2`, evict up to two oldest summaries per successful apply while still adding only one new summary → excess decreases by one per successful apply.

| Pros | Cons |
|------|------|
| Minimal code change (constant + tests) | Still tied to **successful** compression (LLM required to rebalance) |
| Smooth context loss (max 2 summaries per apply) | Softens FR-8 “same count as added” (1:1 → 1:2 eviction cap) |
| Bounded outbox burst (≤2 entries per apply) | Large excess (e.g. +5) needs multiple applies |

**Size estimate:** S

### Alternative B: Eviction-only maintenance pass

Separate `Maintenance` subroutine (no `SummarizerProvider` call): when `summary_count > max_summary_count`, under `conversation_lock`, FIFO-evict oldest summaries into `pending_vectorization` until `count == max` (or cap evictions per tick, e.g. 2, to limit burst). Distinct or extended `Chat.history` audit event.

| Pros | Cons |
|------|------|
| Rebalance **without** LLM; works on any maintenance tick | New orchestration path, predicate, audit shape, tests |
| Clean separation: compress vs enforce inline cap | Extra lock acquisitions per tick when excess present |
| Can drain large excess in one tick (if uncapped) or bounded per tick | Must define interaction order with size/timeout apply on same tick |

**Size estimate:** M

### Alternative C: Do nothing (document only)

Document excess as operator action (raise `max`, manual stash edit). **Out of scope** for this task unless explicitly chosen — task exists to implement A or B.

## Functional requirements

### FR-1: Excess converges to `max_summary_count`

When inline summary count exceeds `max_summary_count`, the chosen alternative restores `count ≤ max` within a **bounded** number of maintenance cycles under a test fixture (exact bound documented in [[design]]).

**Acceptance criteria:**
- [ ] Fixture: 5 inline summaries, `max_summary_count=3`, enough compressible tail for applies — after bounded runs, `count == 3`
- [ ] Steady state unchanged: at `count == max`, one successful apply leaves `count == max`
- [ ] No eviction on compression abort paths (empty chunk, summariser failure)

### FR-2: FR-8 / audit alignment

Eviction still produces `SummaryOutboxEntry` + `Chat.history.evicted` entries per [[TASK-006-compression-apply-and-size-trigger/requirements|TASK-006 FR-8]]; alternative B may add a new `event` type — if so, document in [[design]] and master design.

**Acceptance criteria:**
- [ ] Evicted summaries appear in `pending_vectorization`; absent from `messages`
- [ ] Audit trail reflects evictions (existing `compression` event and/or new event per design)

## Constraints & assumptions

- **Constraint:** Reuse `CompressionApplyCore.evict_summaries_fifo` where possible; no Provider→Provider calls (IODA).
- **Constraint:** Same `conversation_lock` as ingest/compression — no second lock type.
- **Assumption:** Excess is rare; task priority is low until `max_summary_count` tuning or observed production excess.
- **Assumption:** [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] flush remains responsible for draining outbox; this task does not implement flush.

## Out of scope

- `InlineSummaryEnvelope` v2 / full evicted outbox metadata
- Changing compression window or trigger predicates
- Batch eviction of entire excess in one apply without an explicit design decision on burst limits
