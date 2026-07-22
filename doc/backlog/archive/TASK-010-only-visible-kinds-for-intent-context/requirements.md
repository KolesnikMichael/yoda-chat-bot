---
id: TASK-010
doc: requirements
updated: 2026-07-20
---

# TASK-010: only visible kinds for intent context — Requirements

← [[backlog/archive/TASK-010-only-visible-kinds-for-intent-context/task|Back to task]]

## Context

`Mind.process_message_batch` builds a `RoutingContext` after the current batch has
been appended to the conversation. Since
[[TASK-002-user-introduction-on-ingest/task|TASK-002]], a participant's first
message can therefore leave a non-visible `user_introduction` in the candidate
routing tail even after the current user line is excluded. The same unfiltered
path can expose `task_result`, `summary`, and other internal message kinds.

`CognitionCore.build_intent_context_messages` currently applies its tail limit
to all message kinds and serialises them with `to_llm_dict()`. As a result,
intent classification and agent skill selection can receive profile snapshots
or internal task output as recent conversation. This adds irrelevant tokens and
can skew both routing stages.

This task establishes the [[backlog/archive/EPIC-002-agent-routing-reliability/design#Context hygiene|EPIC-002 context-hygiene]]
contract: routing history represents only user-visible conversational
continuity, using the same `user`/`assistant` visibility semantics as memory.

## Functional requirements

### FR-1: Build the routing tail from visible message kinds only

`CognitionCore.build_intent_context_messages` must select recent context by
message `kind`. After omitting the bootstrap prompt and any requested trailing
current-turn entries, it must retain only visible `user` and `assistant`
messages, then apply the tail limit.

**Acceptance criteria:**
- [ ] A candidate message is included only when its `kind` is `user` or `assistant`; `role` alone does not make a message visible.
- [ ] `prompt`, `user_introduction`, `task_result`, and `summary` messages are absent from the returned list.
- [ ] `exclude_trailing` retains its existing meaning: the requested number of current-turn entries is removed from the post-bootstrap conversation before visibility filtering.
- [ ] `limit` is applied after visibility filtering, so interleaved non-visible messages do not displace any of the newest `limit` visible messages.
- [ ] Included messages preserve chronological order and are converted through their existing `Message.to_llm_dict()` representation.
- [ ] A missing conversation, an empty conversation, a bootstrap-only conversation, or a candidate range containing no visible messages returns an empty list.

### FR-2: Supply clean recent context to every routing consumer

The visible-only tail must be the single `RoutingContext.recent_messages`
contract consumed by both intent classification and agent skill selection.

**Acceptance criteria:**
- [ ] `CognitionCore.build_routing_context` continues to derive `current_user_text` from the perceived batch and populates `recent_messages` with the FR-1 result.
- [ ] On first ingest into a new conversation, the newly inserted `user_introduction` and the excluded current user line do not appear in `recent_messages`; with no earlier visible history, the result is empty.
- [ ] When a new participant is introduced in a conversation with earlier visible history, the introduction and current batch are excluded while eligible earlier `user`/`assistant` messages remain available up to the limit.
- [ ] The intent-classification prompt receives no non-visible conversation messages through `RoutingContext.recent_messages`.
- [ ] When the intent is `agent_task`, skill selection receives the same clean `RoutingContext.recent_messages`; profile snapshots and prior `task_result` entries are not reintroduced downstream.

### FR-3: Protect routing-context behavior with regression tests

Automated tests must demonstrate the visibility and ordering contract without
weakening existing visible-history behavior.

**Acceptance criteria:**
- [ ] `tests/test_cognition_intent.py` covers a first-ingest-shaped conversation containing `user_introduction` and verifies that it is absent from the routing tail.
- [ ] The existing cognition case containing `task_result` is tightened to verify exclusion rather than expecting that result in output.
- [ ] A cognition test verifies that the limit counts visible messages when non-visible kinds are interleaved in the candidate tail.
- [ ] Existing tests continue to verify that eligible `user` and `assistant` messages are preserved, ordered newest-last, and passed to the formatted recent-conversation block.
- [ ] `tests/test_agent_provider.py` continues to pass, including coverage that skill selection receives eligible recent messages.
- [ ] The project test suite passes after the change.

## Constraints & assumptions

- **Constraint (epic delivery):** [[backlog/archive/EPIC-002-agent-routing-reliability/epic#Delivery profile|EPIC-002]] has `internal_compat: none`; no criteria are required for deployment between member tasks. Its `external_contract: additive` remains satisfied because this task changes no persisted schema or stored conversation data.
- **Constraint (visibility):** The routing definition of visible kinds must remain semantically aligned with memory's `VISIBLE_KINDS`: exactly `user` and `assistant`.
- **Constraint (IODA):** Filtering remains synchronous, deterministic Core logic. `CognitionCore` must not acquire a dependency on `MemoryCore`, `MemoryProvider`, or another Operation.
- **Constraint:** Tail construction must not mutate the `Conversation` or any `Message`.
- **Constraint:** Existing defaults and public inputs for `build_intent_context_messages`, including the default limit of four and `exclude_trailing`, remain unchanged.
- **Assumption:** Message `kind` is the authoritative visibility signal even when a stored message's LLM `role` differs from its kind.
- **Assumption:** No token, latency, or model-quality threshold is required; deterministic context content and regression coverage are sufficient for this task.

## Out of scope

- Changes to `Conversation.to_llm_messages()` or the history supplied to companion replies.
- Changes to message kinds, persisted conversation schemas, stash migration, introduction insertion, or profile snapshot content.
- Changes to `RoutingContext` fields or to the formatting of its recent-conversation block.
- Broader intent-routing behavior, including `_classify_intent`, `pass` handling, prompt wording, or deterministic command routing.
- Skill-catalog and selection-contract redesign owned by [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/task|TASK-014]].
- New routing telemetry or live-model evaluation.