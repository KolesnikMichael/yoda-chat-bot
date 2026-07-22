---
id: TASK-016
epic: EPIC-002
title: "execution preferences and domain constraints"
status: done
priority: high
size: L
created: 2026-07-20
updated: 2026-07-20
tags:
  - agent
  - preferences
  - web-search
  - constraints
---

# TASK-016: execution preferences and domain constraints

## Description

Pass only the active skill's stored preferences and the current request's explicit constraints into execution, preserving their distinct precedence and persistence semantics. Standardize web-search preferences on the canonical `search_web` key while additively reading legacy `web_search`, and enforce strict source restrictions through `include_domains` without silently widening them.

## Epic

Part of [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Decision 4: Keep profile preferences and request constraints distinct]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Execution context template|Execution context template]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Search web skill prompt|Search web skill prompt]]

## Scope boundary

**In scope:**
- Propagate only active-skill preferences and preserve explicit strict and soft request constraints through execution and scheduled dynamic task distillation.
- Apply the approved precedence from request constraints through stored preferences to skill defaults.
- Write canonical `search_web` preference keys while continuing to read legacy `web_search` values additively.
- Enforce strict web sources with `include_domains` and report no-result limitations without widening the search.

**Out of scope:**
- Timezone inference and DST behavior.
- Grounded outcome rendering, safe-failure wording, or removal of legacy persisted keys.

## Related documents

- [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/design|design]] — architectural solution
- [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/plan|plan]] — implementation plan
- [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: [[backlog/archive/TASK-015-phase-protocol-and-agent-integration/task|TASK-015]]
- Blocks: [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/task|TASK-018]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
