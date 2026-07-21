---
id: TASK-020
epic: EPIC-002
title: "deterministic routing evaluation corpus"
status: todo
priority: medium
size: M
created: 2026-07-20
updated: 2026-07-20
tags:
  - evaluation
  - routing
  - testing
  - multilingual
---

# TASK-020: deterministic routing evaluation corpus

## Description

Create a versioned multilingual routing corpus and deterministic CI harness that scores expected decisions at each stage instead of judging only final prose. The corpus will cover intent, skill, tool or job kind, key arguments, allowed claims, recovery paths, commands, and the motivating July 20 session as a stable regression fixture.

## Epic

Part of [[backlog/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/EPIC-002-agent-routing-reliability/design#Decision 7: Evaluate stages, not only end-to-end replies]]
- [[backlog/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Evaluation contract|Evaluation contract]]
- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Intent classifier|Intent classifier cases]]
- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Skill selection contracts|Skill-selection cases]]

## Scope boundary

**In scope:**
- Define a versioned multilingual fixture schema with expected stage decisions and prohibited or allowed delivery claims.
- Build a deterministic recorded/mock CI harness that reports intent, selection, planning, execution, and delivery failures separately.
- Cover contrastive static/dynamic scheduling, refinements, suspend/resume, malformed output, preferences, commands, and the July 20 scenario.

**Out of scope:**
- Calling live models in normal CI or setting a live-model release threshold.
- Production telemetry transport, dashboards, or prompt/model metadata capture owned by TASK-021.

## Related documents

- [[backlog/TASK-020-deterministic-routing-evaluation-corpus/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/TASK-020-deterministic-routing-evaluation-corpus/design|design]] — architectural solution
- [[backlog/TASK-020-deterministic-routing-evaluation-corpus/plan|plan]] — implementation plan
- [[backlog/TASK-020-deterministic-routing-evaluation-corpus/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[TASK-018-grounded-outcomes-and-safe-failures/task|TASK-018]]
- Blocks: [[TASK-021-stage-telemetry-and-live-eval-runner/task|TASK-021]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
