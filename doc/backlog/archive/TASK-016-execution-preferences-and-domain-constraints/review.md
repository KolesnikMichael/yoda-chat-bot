---
id: TASK-016
doc: review
updated: 2026-07-20
verdict: pass
pytest: pass
---

# TASK-016: execution preferences and domain constraints — Review

← [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/task|Back to task]] | [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

Re-reviewed 29 task-owned paths: 26 tracked modifications and 3 untracked
additions (`execution_context.py`, `test_execution_context_core.py`,
`implementation-notes.md`). Key production surfaces:
`ExecutionContextCore`, `ReactLoop`, `Agent`, session/search/schedule/profile
adapters, `JobDispatcher` / `Mind`, summarizer canonicalize path, and
`search_web` / `AGENTS.md` docs. Diff matches plan Files & artifacts; no
unexpected production subsystems.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `ExecutionContextCore.effective_skill_preferences`; `Agent._activate_skill` / `_upgrade_session_protocol`; `ReactLoop.build_compact_execution_messages` | `test_effective_skill_preferences_*`; `test_run_filters_active_preferences_only_after_selection`; legacy-resume filtering; `test_run_with_skill_filters_active_preferences_only`; delimited profile_data tests | pass |
| FR-2 | `RequestConstraints`; normalize/prepare Core; execution prompt + `search_web` precedence; one-off stays off profile | Core strict-over-soft; `test_direct_selection_applies_strict_precedence_without_persisting_one_off`; `test_direct_selection_materializes_remaining_precedence_tiers` (soft/stored/default); workflow precedence headings | pass |
| FR-3 | `SelectionDecision.request_constraints`; `ScheduleTaskTool`; `JobDispatcher.fire`; `Mind.execute_scheduled_task`; protocol-3 sessions | `test_direct_selection_applies_strict_precedence_without_persisting_one_off` (immediate); `test_scheduled_constraint_survives_selection_persistence_and_dispatch`; schedule/dispatcher/mind payload tests | pass |
| FR-4 | alias/canonicalize in `ExecutionContextCore`, `Agent`, `SummarizerCore`; canonical prompts | Core alias/write tests; agent canonicalize; summarizer dual-key; only-legacy / only-canonical / dual-key Redis fixtures | pass |
| FR-5 | exact-host normalize + prepare gate; `WebSearchTool` / `TavilyApi` `include_domains` | Core inject/accept/reject/refine; Agent conflict no-dispatch; no-results retains restriction; provider propagation | pass |

## Findings

- [x] **Medium** — `yoda/mind/agent/tools/schedule_task_tool.py` / `ScheduleTaskTool.execute` — both paths persist `params.distilled_task` unchanged; byte-stable payload test — `fixed`
- [x] **Medium** — `tests/test_agent.py` / active-preference integration — direct, resume, and `run_with_skill` two-skill filtering — `fixed`
- [x] **Medium** — FR-2 precedence / one-off no-write — `test_direct_selection_applies_strict_precedence_without_persisting_one_off` plus `test_direct_selection_materializes_remaining_precedence_tiers` cover strict override, soft/stored/default materialization, and no profile write on one-off — `fixed`
- [x] **Medium** — scheduled constraint E2E — `test_scheduled_constraint_survives_selection_persistence_and_dispatch` — `fixed`
- [x] **Medium** — only-canonical Redis fixture — `test_user_profile_only_canonical_search_web_reads_and_writes_canonical` — `fixed`
- [x] **Medium** — strict no-results retention — `test_no_results_retry_retains_strict_include_domains` — `fixed`
- [x] **Medium** — `UpdateProfileTool` preference values at DEBUG — `test_update_profile_logs_preference_content_at_debug_only` — `fixed`
- [x] **Medium** — immediate selection → constrained `web_search` — covered by `test_direct_selection_applies_strict_precedence_without_persisting_one_off` — `fixed`

## Follow-ups

- **Info** — Soft/stored web-source preference remains workflow-mediated (Decision 3: Core injects only strict `include_domains`). Soft→stored “override” assertions therefore script the model’s `include_domains` while checking sidecar + profile blocks; no Core soft-injection to assert. Acceptable by design; no code change required.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-20 | fix | Full suite passed (531 tests); seven Medium plan/FR blockers remain open. |
| 2026-07-20 | fix | Re-review: full suite passed (537 tests); six prior findings fixed, with two Medium test-coverage blockers open. |
| 2026-07-20 | pass | Re-review: 541 passed; prior Medium FR-2/FR-3 coverage gaps closed by direct-selection precedence + immediate constrained-search tests. IODA and design contracts hold. |
