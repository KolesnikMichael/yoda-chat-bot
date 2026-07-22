---
id: TASK-015
doc: review
updated: 2026-07-20
verdict: pass-with-follow-ups
pytest: pass
---

# TASK-015: phase protocol and Agent Integration — Review

← [[backlog/TASK-015-phase-protocol-and-agent-integration/task|Back to task]] | [[backlog/TASK-015-phase-protocol-and-agent-integration/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

21 changed paths on `feat/EPIC-002-agent-routing-reliability`: 17 tracked
paths (15 modified, 2 deleted) plus 4 untracked paths. The implementation
replaces `AgentProvider` with `yoda/mind/agent/agent.py`, changes phase Data/Core,
session/language adapters, Mind/startup wiring, agent documentation, and the
planned test modules, including the added malformed-shape API regression test.
Task workflow changes also include `plan.md`, `task.md`, `review.md`, and the
untracked `implementation-notes.md`. No staged files or out-of-scope production
paths were found.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `SelectionDecision`; `ExecutionDecision`; `ReactLoop.validate_selection_decision`; `validate_execution_decision` | `test_SelectionDecision_*`; `test_ExecutionDecision_*`; `test_validate_selection_*`; `test_validate_execution_*` | pass |
| FR-2 | `Agent.run`; `run_with_skill`; phase-specific ReactLoop builders and activation | `test_full_flow_select_skill_and_use_tool`; `test_llm_context_static_system_and_tools_in_activation`; `test_no_skill_returns_unsupported_failure`; suspend/resume and forced-skill tests | pass |
| FR-3 | `ReactLoop.append_correction`; `Agent._parse_selection`; `_parse_execution`; `_handle_phase_issue`; `LanguageProvider.parse_structured` | selection/execution corrective recovery and exhaustion; `test_rejected_execution_never_dispatches_or_enters_history`; `test_execution_retry_budget_survives_successful_tool_iteration`; `test_retry_flag_survives_suspend_resume`; language/API boundary tests | pass |
| FR-4 | `Agent`; `Mind`; startup wiring; deleted `AgentProvider` | `test_agent.py`; `test_parallel_tool_calls_use_gather`; Mind direct/resume/scheduled delegation tests | pass |
| FR-5 | `AgentSessionProvider`; `ReactLoop.upgrade_legacy_protocol`; `Agent.resume` | session legacy inference/round-trip; `test_resume_refreshes_legacy_pre_selection_catalog`; `test_resume_legacy_active_execution_skips_selection`; `test_retry_flag_survives_suspend_resume` | pass |
| FR-6 | `AgentFailure`; typed protocol/iteration exhaustion; stage/category diagnostics; generic `Mind._handle_agent_result` mapping | selection/execution exhaustion; `test_iteration_limit_returns_typed_failure`; rejected-history test; `test_agent_failure_maps_to_generic_instruction`; provider log-level assertion | pass |

## Findings

- [x] **High** — `yoda/mind/agent/core/react_loop.py:464-493` /
  `ReactLoop.upgrade_legacy_protocol` — the legacy pre-selection branch refreshes
  only the catalog seed and leaves `messages[0]` unchanged. A real pre-v2
  session therefore keeps the old combined `Decision` system contract, which
  advertises `tool_calls` / `final_answer` and permits pre-selection
  `ask_user` / `update_profile`, alongside the new selection-only control.
  This makes the deployed compatibility path contradictory, can consume the
  sole corrective budget, and does not satisfy tool-free current selection
  (FR-2, FR-5; design Decision 5; plan 2.4/4.4). Replace the recognized legacy
  base message with `build_selection_system_message`; exercise the path with
  the actual old combined prompt rather than the current `"base system"` /
  `"old combined executor"` placeholders. The Core now recognizes and replaces
  the generated combined contract for both phases, with the legacy prompt
  covered directly and serialized resume paths covered through `Agent`. — `fixed`
- [x] **Medium** — `yoda/api/llm_api.py:119-124` and
  `yoda/mind/perception/language.py:38-46` / structured-output normalization —
  valid JSON with a non-object top level (for example `[]`, a string, or a
  number) reaches `response_format(**data)` and raises `TypeError`.
  `LanguageProvider` catches only `JSONDecodeError` and `ValidationError`, so
  this representative response-shape failure bypasses the phase corrective
  path and escapes the agent instead of consuming its bounded retry (FR-3;
  plan 3.1/7.1). Add boundary coverage and normalize this malformed shape
  without swallowing unrelated provider `TypeError`s. `LLMApi` now uses
  `model_validate`, and `test_parse_chat_async_rejects_non_object_json_as_validation_error`
  covers the malformed top-level shape. — `fixed`
- [x] **Medium** — `yoda/mind/perception/language.py:44-46` /
  `LanguageProvider.parse_structured` — every normalized parse failure emits
  `WARNING Structured output parse failed` without the required stage and
  closed failure category. `Agent` subsequently emits the compliant
  stage/category warning, but the extra non-compliant warning still violates
  FR-6's INFO/WARNING diagnostic contract. Demote the provider event to DEBUG
  or move all WARNING emission to the stage-aware `Agent` boundary, with a log
  assertion. The Provider event is now DEBUG-only and the language test asserts
  that it emits no WARNING-or-higher record. — `fixed`
- [x] **Medium** — `tests/test_agent.py` / FR-5 and FR-6 integration coverage —
  the suite loads a serialized legacy active-execution session and separately
  unit-tests its Core message upgrade, but never resumes that serialized
  session through `Agent.resume` to completion. It also has no orchestration
  test for typed iteration-limit exhaustion, rejected execution decisions
  dispatching no tools, retry-budget persistence across a successful tool
  iteration, or rejected execution payloads remaining absent from accepted
  history. These scenarios are explicit in plan 4.3/4.4/7.1 and the
  FR-3/FR-5/FR-6 acceptance criteria, so the claimed all-AC coverage is
  incomplete despite the green suite. The suite now covers serialized active
  execution resume, rejected dispatch/history, retry persistence across a
  successful tool iteration, and typed iteration exhaustion. — `fixed`

## Follow-ups

- **Low** — strengthen Core unit coverage for blank `selected_skill`, empty
  `call_tools.tool_calls`, `no_skill` without `reason="unsupported"`, and the
  exhausted execution correction no-op. Runtime guards exist, but these
  representative FR-1/FR-3 cases are not asserted directly.
- **Low** — make the general session round-trip fixture internally consistent:
  it currently combines `active_skill` with the default `phase=selection`.
- **Low** — update `yoda/mind/agent/AGENTS.md` legacy-upgrade wording: the
  pre-selection path now replaces a recognized combined base system contract
  as well as refreshing the catalog seed, while the current text names only
  the seed refresh.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-20 | fix | 471 tests pass; legacy selection upgrade, malformed-shape normalization, diagnostics, and required integration coverage need fixes. |
| 2026-07-20 | pass-with-follow-ups | 476 tests pass; all prior High/Medium findings fixed, with only low-risk test/documentation follow-ups remaining. |
