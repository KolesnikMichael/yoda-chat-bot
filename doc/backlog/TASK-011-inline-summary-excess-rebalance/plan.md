---
id: TASK-011
doc: plan
updated: 2026-06-18
last_step: 
branch: 
---

# TASK-011: inline summary excess rebalance — Implementation plan

← [[task|Back to task]] | [[requirements|Requirements]] | [[design|Design]]

## Overview

Implement the rebalance strategy chosen in [[design#Decision 1: Rebalance strategy]] so inline summary count above `max_summary_count` converges to `max` without leaving excess stuck at `max + k`. Blocked on design decision (Alternative A vs B).

## Goal / Non-goals

- **Goal:** Bounded convergence from excess → `max` in tests; steady-state 1:1 behaviour preserved at `count == max`.
- **Non-goals:** Envelope v2 metadata; flush/outbox implementation; compression algorithm changes.

## Context to load

- [[requirements]] — problem statement, alternatives, FR-1…FR-2
- [[design]] — chosen strategy (must be filled before implementation)
- [[TASK-006-compression-apply-and-size-trigger/design]] — eviction cap as-built notes
- [[EPIC-001-chat-context-management/epic|EPIC-001]] + master design — FIFO eviction step 7
- `yoda/mind/maintenance.py`, `yoda/mind/memory/compression_apply_core.py`
- Root `AGENTS.md`, `coding_behavior.md`

## Pre-flight

- [ ] On shared epic branch: `git checkout feat/EPIC-001-chat-context-management`
- [ ] [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] merged on branch
- [ ] Design Decision 1 resolved in [[design]]
- [ ] Baseline tests green: `.venv/bin/python -m pytest`

## Files & artifacts

| Path | IODA | Op | FR |
|------|------|----|----|
| `yoda/mind/maintenance.py` | Integration | edit | FR-1 |
| `tests/test_compression_apply.py` | Test | edit | FR-1 |
| `tests/test_maintenance.py` | Test | edit (Alt B) | FR-1 |

## Stages

### Stage 1: Implement chosen alternative

**Goal:** Code + unit tests for excess convergence.

- [ ] **1.1** Apply design choice
  - Files: per [[design#System impact]]
  - Action: Alternative A — change `summaries_added` to `2`; Alternative B — add eviction-only subroutine + wire into maintenance tick
  - Verify: `.venv/bin/python -m pytest tests/test_compression_apply.py -k excess`
  - Commit: `feat(TASK-011): 1.1 rebalance policy`

- [ ] **1.2** Steady-state regression
  - Files: `tests/test_compression_apply.py`
  - Action: assert `count == max` unchanged after one apply at cap
  - Verify: `.venv/bin/python -m pytest tests/test_compression_apply.py`
  - Commit: `test(TASK-011): 1.2 steady state`

### Stage 2: Test sweep

- [ ] **2.1** Full suite
  - Verify: `.venv/bin/python -m pytest`
  - Commit: `test(TASK-011): 2.1 full suite`

## FR coverage (traceability)

| FR | Steps | Verification |
|----|-------|--------------|
| FR-1 | 1.1, 1.2, 2.1 | `test_compression_apply.py` excess fixture |
| FR-2 | 1.1 | audit + outbox assertions |

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Alternative B tick ordering vs compression | Medium | Medium | Design Decision 2; integration test same tick |
| FR-8 wording drift | Low | Low | Update TASK-006 requirements cross-ref if cap=2 |

## Rollback

- Code: `git revert` on epic branch.
- State: in-memory only; no Redis migration.

## Definition of Done

- [ ] All plan steps checked
- [ ] FR-1…FR-2 acceptance criteria pass
- [ ] Full suite green: `.venv/bin/python -m pytest`
- [ ] `task.md`: `status: done`, `updated: <date>`
- [ ] `design.md` Decision 1 filled; master design updated if Alternative B adds audit event
