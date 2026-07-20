---
id: TASK-017
doc: review
updated: 2026-07-21
verdict: pass-with-follow-ups
pytest: pass
---

# TASK-017: IANA timezone execution guidance — Review

← [[backlog/TASK-017-iana-timezone-execution-guidance/task|Back to task]] | [[backlog/TASK-017-iana-timezone-execution-guidance/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

Re-reviewed 14 task-related changed/untracked files, excluding this review output:
six implementation/workflow files under `yoda/mind/agent/`, five test files, and
three task-control documents (`plan.md`, `task.md`, `implementation-notes.md`).
The implementation paths match the plan; no resolver, schema migration, new IODA
dependency, or other out-of-scope production subsystem was added.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `ScheduleCore.validate_timezone_name` / `relative_timezone_name`; both scheduling tools; both skill specs | Core helper tests; static/dynamic profile, explicit, inference, relative, missing, and invalid-profile agent cases | weak |
| FR-2 | Strict tool validation; `ask_user` guidance in both skill specs | Static/dynamic unresolved and offset-resume agent cases; mirrored absolute/cron bad-timezone boundary tests | pass |
| FR-3 | Inference/persistence guidance in both skill specs; existing `update_profile` path | Static/dynamic inference tests assert both fields, explicit schedule timezone, and subsequent reuse | pass |
| FR-4 | `ZoneInfo` validation/conversion; `CronTrigger`; strict scheduling boundaries | Absolute/cron DST tests; static/dynamic rejection-before-side-effect, partial-absolute, propagation, metadata, and relative-fallback tests | weak |

## Findings

- [x] **Medium** — `yoda/mind/agent/tools/schedule_message_tool.py` and `schedule_task_tool.py` / timing-mode validation — both tools now reject any partial absolute field set before mode selection, with relative/cron regression tests asserting no scheduler or storage side effect — `fixed`
- [x] **Medium** — `tests/test_agent.py` / TASK-017 execution scenarios — deferred `search_web` now mirrors missing, invalid-profile, offset-only clarification/no-dispatch, inferred-profile reuse, and valid-resume/reuse scenarios — `fixed`
- [x] **Medium** — `tests/test_schedule_task_tool.py` / `ScheduleTaskTool` boundary coverage — dynamic scheduling now directly covers absolute missing/invalid/offset rejection, relative profile/UTC fallback, partial absolute fields, and unchanged IANA/constraints propagation — `fixed`
- [ ] **Low** — `tests/test_skill_catalog.py` / `_assert_iana_timezone_workflow` — the test checks policy keywords but not the required explicit → profile → location → clarify ordering, so reordering the prompt contract would still pass plan 3.1/3.2 coverage — `open`
- [ ] **Low** — `yoda/mind/agent/core/schedule_core.py` / `validate_timezone_name` — validation strips whitespace before `ZoneInfo`, and both tools persist the stripped value. This accepts a name not accepted exactly as supplied and does not pass it unchanged, contrary to the design interface and plan 1.1/2.1/2.2 wording — `open`

## Follow-ups

- **Low:** Strengthen catalog tests to assert explicit → profile → location →
  clarification ordering.
- **Low:** Either reject whitespace-padded timezone names or explicitly reconcile
  normalization with the design contract.
- **Info:** Redis/live-scheduler smoke remains skipped as documented in
  `implementation-notes.md`; all 601 automated tests passed.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-20 | fix | 586 tests passed; three Medium contract/coverage findings remain open |
| 2026-07-21 | pass-with-follow-ups | 601 tests passed; all Medium findings fixed, two Low follow-ups remain |
