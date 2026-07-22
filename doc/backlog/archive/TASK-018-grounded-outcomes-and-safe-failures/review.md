---
id: TASK-018
doc: review
updated: 2026-07-21
verdict: pass
pytest: pass
---

# TASK-018: grounded outcomes and safe failures — Review

← [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/task|Back to task]] | [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

31 modified/untracked paths are visible (25 tracked and 6 untracked), including
this review output and `implementation-notes.md`; 29 implementation/task-contract
paths were reviewed. Key paths are the new outcome/delivery Data and Core modules,
the `Agent`/session/tool wiring, `Mind`, `JobDispatcher`, memory prefix
compatibility, and their tests. `tests/test_react_loop.py` is an additional but
relevant Stage 5.1 test file.

Full suite: **652 passed, 1 warning in 5.09s**.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `outcome_data.py`; `agent_data.py` / `AgentResult`; `agent.py`; `session_provider.py` | exclusivity/immutability tests; direct/resume/forced paths; session round-trip | pass |
| FR-2 | `OutcomeCore.evidence_from_results` / `success_from_terminal` / `success_from_finish`; terminal tool adapters; `Agent._execute_loop` | Core evidence/success tests; mixed-evidence terminal failure; throwing terminal tool; successful retry | pass |
| FR-3 | `DeliveryCore._success_payload` / `build_instruction`; `Mind._deliver_via_core` | message/task/no-job claims; exact schedule round-trip in instruction facts; adversarial delimiter round-trip; grounded instruction | pass |
| FR-4 | `JobDispatcher.fire`; `Mind.deliver_scheduled_reminder` / `execute_scheduled_task` | legacy/one-shot/recurring message/task routing; Mind static-trigger policy | pass |
| FR-5 | `OutcomeCore.failure`; Agent failure paths; `Mind.notify_scheduled_failure`; dispatcher exception path | Core categories; Agent unsupported/no-evidence/failed-terminal/throwing-terminal paths; Mind/dispatcher failures | pass |
| FR-6 | `DeliveryCore.build_payload` / `build_instruction`; `Mind._deliver_via_core` | semantic payload tests and Mind instruction inspection | pass |
| FR-7 | `AgentSessionProvider`; `ReactLoop.upgrade_legacy_protocol`; dispatcher legacy job routing; `KNOWN_TASK_RESULT_PREFIXES` | protocol-1/2/3 Agent resume; suspend/evidence/resume; Provider round-trip; dispatcher; memory compatibility | pass |

## Findings

- [x] **Medium** — `yoda/mind/agent/core/delivery_core.py` /
  `DeliveryCore._success_payload` — an exact user-relevant schedule reaches
  `ExecutionOutcome.schedule`, but the authoritative delivery payload reduces it
  to `schedule_present=true`; neither `DeliveryPayload` nor the serialized
  instruction retains the schedule value. A valid outcome with summary
  `"Reminder created."` and schedule
  `"2026-07-22 09:00 Europe/Berlin"` therefore gives the renderer no authorized
  schedule to report. This misses FR-3 acceptance criterion 1 and plan 3.1/7.1.
  Preserve the exact schedule as untrusted payload data/fact and assert its
  round-trip for message and task outcomes — `fixed`
- [x] **High** — `yoda/mind/agent/agent.py` / `Agent._execute_loop` and
  `yoda/mind/agent/core/outcome_core.py` / `success_from_finish` — a failed
  terminal tool is discarded from structured decision state, so a later
  `finish` can still be authorized by earlier successful evidence for the same
  broad operation. For example, successful `text_to_image` followed by failed
  `send_picture` produces a successful `create_picture/information` outcome and
  `operation_completed`; `get_user_data` followed by failed
  `delete_user_data` has the same shape. This violates FR-2/FR-5 and design
  Decision 2. `AgentContext.terminal_failure_pending` now survives persistence,
  blocks `finish`, and a successful terminal retry still completes; Agent tests
  cover mixed evidence and retry — `fixed`
- [x] **Medium** — `yoda/mind/agent/data/outcome_data.py` /
  `ExecutionOutcome.__post_init__` — a non-`scheduled_job` success accepts
  `schedule` and `scheduled_operation`. `DeliveryCore` then emits
  `schedule_present=true` / `scheduled_operation` alongside an unscheduled
  result, creating a contradictory authoritative payload (FR-1, FR-3; design
  Data model). Restrict schedule fields to scheduled-job outcomes and
  `scheduled_operation` to `job_kind=task`, with constructor tests — `fixed`
- [x] **Medium** — `yoda/mind/agent/data/agent_data.py` / `AgentResult` — the
  exclusive wrapper is mutable despite the frozen design contract. Valid
  construction can be mutated afterward to contain neither or both alternatives,
  bypassing the FR-1 invariant. Make the dataclass frozen and test mutation
  rejection — `fixed`
- [x] **Medium** — `tests/test_agent.py` — the terminal-failure test returns a
  normal `success=False` result; it does not exercise a terminal tool that
  raises and is converted by `Agent._execute_single_tool`. FR-5 and plan 2.2/7.1
  explicitly require deterministic terminal-tool exception coverage. Add an
  Agent-level throwing terminal fake and assert a transient outcome with no
  result/job/side-effect claim — `fixed`
- [x] **Medium** — `tests/test_agent.py`, `tests/test_agent_session.py`, and
  `tests/test_react_loop.py` — compatibility tests resume protocol 1 through
  `Agent`, load only a limited protocol-2 provider fixture, and round-trip
  evidence only at Provider level. They do not resume representative protocol-2
  and protocol-3 active sessions through protocol 4, or prove that evidence
  saved on suspension survives `Agent.resume` and authorizes a post-resume
  finish. Protocol-2/3 Agent resume and suspend/evidence/resume tests now cover
  those paths — `fixed`
- [x] **High** — `yoda/mind/agent/core/delivery_core.py` /
  `DeliveryCore.build_instruction` — `json.dumps()` does not escape `<` or `>`.
  A source string containing `</delivery_data>` therefore closes the
  `trust="untrusted"` block and places the remainder in apparent control text.
  This defeats the authoritative claim boundary for outcome summaries,
  clarifications, and stored reminders (FR-3, FR-6; design Decision 4; plan
  3.2). Escape delimiter-significant characters (or use an encoding that cannot
  contain the delimiter) and add an adversarial round-trip test — `fixed`
- [x] **Medium** — `tests/test_job_dispatcher.py` — the planned task diff adds no
  trigger-time coverage for one-shot versus recurring message/task jobs.
  Existing tests route one message and one task but do not prove recurrence
  preserves the static-versus-dynamic claim boundary required by FR-4 (plan
  6.2, 7.1) — `fixed`
- [x] **Medium** — `tests/test_agent.py` — Agent-level acceptance coverage is
  missing for three core trust paths: `fail/unsupported`, a valid `finish`
  without evidence, and a failed terminal tool that must not produce success or
  a job/side-effect claim. Core/validation/tool tests cover pieces, but not the
  orchestration contract required by FR-2 and FR-5 (plan 5.2, 7.1) — `fixed`

## Follow-ups

- None blocking. Manual AC spot-check (plan 7.2) was skipped per
  `implementation-notes.md`; deterministic Stage 7.1 coverage is sufficient for
  close.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-21 | fix | 632 tests pass; delivery delimiter injection and explicit FR test gaps remain |
| 2026-07-21 | fix | 640 tests pass; prior findings fixed, but mixed-evidence success, Data invariants, and explicit AC test gaps still block |
| 2026-07-21 | fix | 650 tests pass; prior blockers fixed, but the exact schedule is omitted from the authoritative delivery payload |
| 2026-07-21 | pass | 652 tests pass; schedule round-trip restored; all prior findings fixed; IODA and non-goals verified |
