---
id: TASK-014
epic: EPIC-002
title: "discriminative skill selection contracts"
status: done
priority: high
size: M
created: 2026-07-20
updated: 2026-07-20
tags:
  - agent
  - routing
  - skills
  - prompts
---

# TASK-014: discriminative skill selection contracts

## Description

Make skill selection depend on a compact, discriminative catalog contract instead of broad descriptions or catalog order. Each skill will expose positive triggers, negative boundaries, and contrastive examples so the selector can reliably distinguish static scheduled messages from dynamic tasks, while selection and other control-plane instructions use an authoritative role.

## Epic

Part of [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Selection contract versus execution workflow]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Static message versus dynamic task]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Decision 3: Make selection metadata discriminative]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Decision 8: Use system role for control-plane messages]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Skill-selection prompt|Skill-selection prompt]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Skill selection contracts|Skill selection contracts]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Message-role contract|Message-role contract]]

## Scope boundary

**In scope:**
- Define catalog-facing selection metadata for when to use, when not to use, and contrastive examples.
- Encode and test the static-message versus dynamic-task selection boundary independently of catalog order.
- Use the `system` role for skill catalog and selection control-plane messages while retaining user-authored data as `user`.

**Out of scope:**
- Phase-specific execution models, clarification, retries, and Agent orchestration.
- Full skill workflows, tool schemas, execution preferences, and outcome delivery.

## Related documents

- [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/design|design]] — architectural solution
- [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/plan|plan]] — implementation plan
- [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[backlog/archive/TASK-010-only-visible-kinds-for-intent-context/task|TASK-010]]
- Blocks: [[backlog/archive/TASK-015-phase-protocol-and-agent-integration/task|TASK-015]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
