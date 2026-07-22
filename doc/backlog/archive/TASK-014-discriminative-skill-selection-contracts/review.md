---
id: TASK-014
doc: review
updated: 2026-07-20
verdict: pass
pytest: pass
---

# TASK-014: discriminative skill selection contracts — Review

← [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/task|Back to task]] | [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

22 changed paths on `feat/EPIC-002-agent-routing-reliability`: 21 modified
files (1,405 insertions, 138 deletions) plus the untracked
`implementation-notes.md`. The implementation touches the
planned `SkillSummary`, catalog loader, `ReactLoop`, `AgentProvider`, production
and fixture skill specs, four test modules, and agent-module documentation.
Task planning artifacts (`task.md`, `design.md`, `plan.md`) are also modified as
part of the task workflow. No staged files are present.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `SkillSummary`; `SkillCatalog.load_catalog`; five production and three fixture specs | `test_skill_summary_*`; `test_load_catalog_loads_selection_metadata`; `test_validate_selection_metadata_*`; `test_load_catalog_missing_name_raises` | pass |
| FR-2 | `ReactLoop.build_selection_control_message`; `SkillCatalog.public_summaries` | `test_build_selection_control_message_*`; `test_production_public_summaries_excludes_manage_user_data`; provider role tests | pass |
| FR-3 | `schedule_message.md`; `search_web.md`; canonical name sorting in `ReactLoop` | `test_production_catalog_static_dynamic_contrasts`; `test_build_selection_control_message_name_sort_stable` | pass |
| FR-4 | Split selection builders; system activation/nudge; structurally matched `refresh_selection_messages` seeds | `test_selection_includes_recent_messages`; `test_llm_context_static_system_and_tools_in_activation`; `test_execution_nudge_uses_system_role`; `test_selection_keeps_instruction_like_user_text_out_of_system_control`; adversarial marker/delimiter refresh tests | pass |
| FR-5 | Additive `SkillSummary` defaults; session round-trip; exact legacy-suffix pre-selection refresh | `test_load_legacy_catalog_summaries_defaults_selection_fields`; `test_save_load_preserves_selection_contract_fields`; `test_resume_refreshes_legacy_pre_selection_catalog`; `test_refresh_selection_messages_legacy_preserves_delimiters_in_user_data` | pass |

## Findings

- [x] **High** — `yoda/mind/agent/core/react_loop.py:118-174` /
  `ReactLoop.refresh_selection_messages` — seed recognition searches every
  message for raw marker substrings and splits a legacy user message at the
  first `Available skills:` / `No skills available.` occurrence. Consequently,
  user-authored task or quoted conversation text containing those literals can
  be mistaken for control structure: a legacy task is truncated, while a
  new-format task containing `<skill_selection_control>` raises
  `ValueError` on resume. A legacy user message containing both XML markers can
  also be replaced with a `system` control message. Reproduced locally with
  `"explain the label Available skills: literally"` (the refreshed payload
  retained only `"explain the label"`) and with a new-format task containing
  `<skill_selection_control>` (resume raised “multiple selection seed
  markers”). Identify seeds structurally by expected role/position and match
  the generated legacy delimiter rather than arbitrary user substrings; add
  adversarial delimiter/marker tests. This violates FR-4 user-data trust
  boundaries and FR-5/design Decision 5 preservation guarantees (plan steps
  3.3, 5.2, 7.1). Re-review verified role/wrapper structural matching for the
  new format, exact persisted-catalog suffix matching for the legacy format,
  adversarial regression coverage, and preservation of subsequent messages.
  — `fixed`

## Follow-ups

- None.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-20 | fix | 438 tests pass; resumed selection can misclassify or truncate user-authored marker text. |
| 2026-07-20 | pass | Blocking refresh finding fixed; 440 tests pass. |
