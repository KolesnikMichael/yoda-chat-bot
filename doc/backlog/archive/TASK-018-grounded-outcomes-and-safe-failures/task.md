---
id: TASK-018
epic: EPIC-002
title: "grounded outcomes and safe failures"
status: done
priority: high
size: M
created: 2026-07-20
updated: 2026-07-21
tags:
  - agent
  - outcomes
  - safety
  - delivery
---

# TASK-018: grounded outcomes and safe failures

## Description

Ground every user-visible completion in a structured execution outcome that records what operation succeeded or failed and what tool or job kind actually resulted. Delivery must not claim that a static scheduled message performs a live task, and failures must offer a useful capability-agnostic next step without exposing skill, phase, schema, model, provider, storage, or other implementation details.

## Epic

Part of [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Truthful completion]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Static message versus dynamic task]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Decision 9: Keep safe failures capability-agnostic]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Grounded delivery prompts|Grounded delivery prompts]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Schedule message skill prompt|Schedule-message guardrail]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Search web skill prompt|Search-web guardrail]]

## Scope boundary

**In scope:**
- Define structured success and failure outcomes carrying operation, status, and resulting tool/job kind.
- Constrain rendered completion claims to the actual outcome, including prohibiting live-task claims for static messages.
- Map ambiguous, transient, and unsupported failures to safe next steps without implementation details.
- Test factual claim boundaries and safe error rendering independently of voice or exact free-form wording.

**Out of scope:**
- Selection metadata, phase orchestration, execution preference/timezone propagation, and evaluation runners.
- Operational cancellation or migration of jobs from the motivating test session.

## Related documents

- [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/design|design]] — architectural solution
- [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/plan|plan]] — implementation plan
- [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/task|TASK-016]], [[backlog/archive/TASK-017-iana-timezone-execution-guidance/task|TASK-017]]
- Blocks: [[backlog/archive/TASK-020-deterministic-routing-evaluation-corpus/task|TASK-020]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
