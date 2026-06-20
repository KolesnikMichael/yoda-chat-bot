---
id: TASK-011
epic: EPIC-001
title: "inline summary excess rebalance"
status: todo
priority: low
size: S
created: 2026-06-18
updated: 2026-06-18
tags:
  - chat-context
---

# TASK-011: inline summary excess rebalance

## Description

Follow-up from [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] close-out.

When `kind == "summary"` count exceeds `ChatCompressionSettings.max_summary_count`, `CompressionApplyCore.evict_summaries_fifo` evicts at most `summaries_added` blocks per successful apply (`Maintenance` passes `summaries_added=1`). Each successful compression still **adds** one new summary, so net summary count is unchanged when already above the cap — excess never self-corrects (e.g. after lowering `max_summary_count` or corrupted state). FR-8 intended a 1:1 exchange per run; that holds in the steady state but traps anomalous excess.

Pick and implement one rebalance strategy (see **Solution alternatives** in [[requirements]]), update FR-8 / master design if needed, and add tests proving convergence from excess → `max`.

## Master design

- [[chat_context_management#Compression apply]] — transformation step 7 (FIFO eviction)
- [[TASK-006-compression-apply-and-size-trigger/design#As-built notes (close-out reconciliation)]]

## Program

Part of the Chat Context Management chain — see [[EPIC-001-chat-context-management/epic|EPIC-001]]. Not on the critical path to TASK-007/008/009; defer until excess is observed or before merge if `max_summary_count` tuning is planned.

## Scope boundary

**In scope:**
- Rebalance policy when inline summary count > `max_summary_count` (see requirements alternatives)
- Tests: fixture with excess summaries converges to `max` within bounded successful applies (or eviction-only ticks)
- Requirements / design / FR-8 alignment

**Out of scope:**
- Enriching evicted `SummaryOutboxEntry` metadata (envelope v2 — separate concern; may pair with [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]])
- Changing `CompressionCore` window algorithms
- Timeout-trigger wiring ([[TASK-007-timeout-trigger-wiring/task|TASK-007]])

## Related documents

- [[requirements]] — problem statement and solution alternatives
- [[design]] — chosen approach (filled at design time)
- [[plan]] — implementation plan
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — epic decomposition and master design

## Dependencies

- Depends on: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]
- Blocks:

## Notes

Discovered during TASK-006 close-out (eviction cap divergence). Default recommendation in requirements: **Alternative A (cap=2)** unless product requires rebalance without extra LLM calls — then **Alternative B**.
