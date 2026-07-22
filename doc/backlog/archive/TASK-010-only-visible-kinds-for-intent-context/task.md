---
id: TASK-010
epic: EPIC-002
title: "only visible kinds for intent context"
status: done
priority: medium
size: XS
created: 2026-06-14
updated: 2026-07-20
tags:
  - cognition
  - routing
---

# TASK-010: only visible kinds for intent context

## Description

Side effect of [[TASK-002-user-introduction-on-ingest/task|TASK-002]]: after first user ingest,
`Mind.process_message_batch` builds routing context from the conversation *after*
`append_conversation_line` has inserted a `user_introduction`. `CognitionCore.build_intent_context_messages`
maps the message tail through `to_llm_dict()` with no kind filter, so intent classification and
agent skill selection receive the full profile snapshot in their "Recent conversation" block — noise
that can skew routing and wastes tokens.

Filter `RoutingContext.recent_messages` to `VISIBLE_KINDS` (`user`, `assistant`) only. The same
path currently also includes other non-visible kinds (e.g. `task_result`); align with the visibility
contract in `memory.py` rather than special-casing `user_introduction` alone.

## Epic

Part of [[backlog/archive/EPIC-002-agent-routing-reliability/epic|EPIC-002]] — read the epic
(decomposition, shared branch) and its master design first for cross-task context.

## Master design

- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Context hygiene]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design#Proposed delivery sequence]]

## Suggested prompts

- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Intent classifier|Intent classifier]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/suggested_prompts#Message-role contract|Message-role contract]]

## Scope boundary

**In scope:**
- Filter tail selection in `CognitionCore.build_intent_context_messages` by visible kinds before applying `limit`
- Tests in `tests/test_cognition_intent.py`: first-ingest fixture with `user_introduction`; tighten test that currently expects `task_result` in output
- Confirm agent pipeline tests still pass (`test_agent_provider.py`)

**Out of scope:**
- Changes to LLM reply history (`to_llm_messages()`)
- Broader routing redesign (`_classify_intent` naming, `pass` handling, etc.)

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[review]] — plan-compliance gate (verdict + findings)

## Dependencies

- Depends on: [[TASK-002-user-introduction-on-ingest/task|TASK-002]] (introduces `user_introduction` on first ingest)
- Blocks: [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/task|TASK-014]]

## Notes

Discovered during TASK-002 close-out.
