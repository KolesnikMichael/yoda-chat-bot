---
id: TASK-021
epic: EPIC-002
title: "stage telemetry and live eval runner"
status: done
priority: medium
size: M
created: 2026-07-20
updated: 2026-07-22
tags:
  - telemetry
  - evaluation
  - agent
  - prompts
---

# TASK-021: stage telemetry and live eval runner

## Description

Add stage-labelled diagnostics and an on-demand live-model evaluation runner over the versioned corpus so routing regressions can be attributed to intent, selection, planning, execution, or delivery. Live runs record model identity, prompt hash, corpus version, and stage metrics but remain non-blocking because network cost, rate limits, model drift, and residual nondeterminism make them unsuitable for initial PR gating.

## Epic

Part of [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Decision 7: Evaluate stages, not only end-to-end replies]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Stage-local correctness]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Prompt identity and logging|Prompt identity and logging]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Evaluation contract|Evaluation contract]]

## Scope boundary

**In scope:**
- Emit stage-specific diagnostics without logging user content above the project's debug-level policy.
- Capture model identity, prompt hash, corpus version, and per-stage metrics for live evaluation runs.
- Provide an on-demand non-blocking live-model runner that consumes the TASK-020 corpus and reports stage results.

**Out of scope:**
- Making live evaluation PR-blocking, defining release thresholds, or scheduling mandatory remote runs.
- Changing corpus expectations, routing behavior, or user-visible outcomes to accommodate model variance.

## Related documents

- [[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/design|design]] — architectural solution
- [[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/plan|plan]] — implementation plan
- [[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[backlog/archive/TASK-020-deterministic-routing-evaluation-corpus/task|TASK-020]]
- Blocks: None.

## Notes

<!-- Short operational notes, decisions made on the fly -->
