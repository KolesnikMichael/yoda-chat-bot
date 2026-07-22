---
id: TASK-015
epic: EPIC-002
title: "phase protocol and Agent Integration"
status: done
priority: high
size: L
created: 2026-07-20
updated: 2026-07-20
tags:
  - agent
  - routing
  - ioda
  - validation
---

# TASK-015: phase protocol and Agent Integration

## Description

Make agent execution phase-safe by separating skill-selection and execution response models, selecting a skill before any workflow-specific clarification, and permitting one bounded corrective retry for malformed model output. Move phase and tool orchestration behind a bare-noun `Agent` Integration so pure transition policy and infrastructure adaptation remain in their proper IODA layers.

## Epic

Part of [[backlog/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/EPIC-002-agent-routing-reliability/design#Stage-local correctness]]
- [[backlog/EPIC-002-agent-routing-reliability/design#Decision 1: Choose the skill before clarification]]
- [[backlog/EPIC-002-agent-routing-reliability/design#Decision 2: Use phase-specific response models]]
- [[backlog/EPIC-002-agent-routing-reliability/design#Decision 10: Put agent orchestration in an Integration]]
- [[backlog/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Phase-specific agent prompts|Phase-specific agent prompts]]
- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Corrective retry prompts|Corrective retry prompts]]
- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Message-role contract|Message-role contract]]

## Scope boundary

**In scope:**
- Define separate strict typed outputs for selection and execution, including stage-local validation.
- Select the skill before clarification and apply one corrective retry before returning a structured failure.
- Establish the IODA `Agent` Integration as the orchestration boundary with pure policy in Core and infrastructure in Providers.
- Cover selection, clarification, retry exhaustion, and orchestration boundaries with deterministic tests.

**Out of scope:**
- Skill catalog metadata owned by TASK-014.
- Execution preference/domain propagation, timezone guidance, grounded delivery, and evaluation infrastructure.

## Related documents

- [[backlog/TASK-015-phase-protocol-and-agent-integration/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/TASK-015-phase-protocol-and-agent-integration/design|design]] — architectural solution
- [[backlog/TASK-015-phase-protocol-and-agent-integration/plan|plan]] — implementation plan
- [[backlog/TASK-015-phase-protocol-and-agent-integration/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[TASK-014-discriminative-skill-selection-contracts/task|TASK-014]]
- Blocks: [[TASK-016-execution-preferences-and-domain-constraints/task|TASK-016]], [[TASK-017-iana-timezone-execution-guidance/task|TASK-017]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
