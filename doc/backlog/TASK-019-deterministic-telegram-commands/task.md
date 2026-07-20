---
id: TASK-019
epic: EPIC-002
title: "deterministic Telegram commands"
status: todo
priority: medium
size: S
created: 2026-07-20
updated: 2026-07-20
tags:
  - telegram
  - commands
  - routing
  - portal
---

# TASK-019: deterministic Telegram commands

## Description

Route recognized Telegram interface commands deterministically in the Portal so `/reset`, `/start`, `/help`, and `/settings` never depend on LLM intent classification. Define and test an explicit fallback for unknown slash commands while leaving ordinary messages on the existing routing path.

## Epic

Part of [[backlog/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/EPIC-002-agent-routing-reliability/design#Decision 6: Handle interface commands deterministically]]
- [[backlog/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/EPIC-002-agent-routing-reliability/suggested_prompts#Prompt boundary|Prompt boundary — commands bypass LLMs]]

## Scope boundary

**In scope:**
- Intercept `/reset`, `/start`, `/help`, and `/settings` in the Telegram Portal before LLM routing.
- Define deterministic handling for command arguments and an explicit unknown-command fallback.
- Test recognized-command bypass, unknown-command fallback, and unchanged ordinary-message routing.

**Out of scope:**
- Adding new Telegram commands or redesigning existing command semantics.
- Probabilistic intent, skill selection, phase execution, and command telemetry beyond test seams.

## Related documents

- [[backlog/TASK-019-deterministic-telegram-commands/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/TASK-019-deterministic-telegram-commands/design|design]] — architectural solution
- [[backlog/TASK-019-deterministic-telegram-commands/plan|plan]] — implementation plan
- [[backlog/TASK-019-deterministic-telegram-commands/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — epic decomposition and master design

## Dependencies

- Depends on: None.
- Blocks: [[TASK-020-deterministic-routing-evaluation-corpus/task|TASK-020]]

## Notes

<!-- Short operational notes, decisions made on the fly -->
