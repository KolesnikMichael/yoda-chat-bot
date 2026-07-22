---
id: TASK-020
doc: review
updated: 2026-07-21
verdict: pass-with-follow-ups
pytest: pass
---

# TASK-020: deterministic routing evaluation corpus — Review

← [[backlog/archive/TASK-020-deterministic-routing-evaluation-corpus/task|Back to task]] | [[backlog/archive/TASK-020-deterministic-routing-evaluation-corpus/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

Re-review after prior `fix` (FR-6 selection `recovery: corrected` gap). Working
tree matches plan Files & artifacts: `yoda/mind/evaluation/` (Data/Core/Provider),
`tests/routing_evaluation/` harness + recorded adapters,
`tests/fixtures/routing_evaluation/corpus-v1.json` (schema 1 / corpus **1.1.1**,
**26** cases including `en-selection-protocol-corrected`), three
`tests/test_routing_*.py` modules, and `yoda/mind/agent/AGENTS.md`. Extra
maintenance generator `tests/fixtures/routing_evaluation/build_corpus.py`
(documented in implementation-notes) plus EPIC-002 doc churn outside the plan
file table.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `yoda/mind/evaluation/data.py`; `corpus_provider.py`; `core.py::validate_corpus` | `test_unknown_top_level_field_rejected`; `test_load_invalid_field_identifies_case_and_field`; `test_load_valid_corpus`; `test_validate_corpus_reports_duplicate_case_id` | pass |
| FR-2 | `core.py::validate_corpus`; `corpus-v1.json` (26 cases) | `test_corpus_has_en_and_ru_intent_families`; `test_corpus_covers_all_discovered_skills`; `test_corpus_contains_required_contrastive_families` | pass |
| FR-3 | `tests/routing_evaluation/fakes.py`; `harness.py`; gate | `test_recorded_llm_*`; `test_routing_evaluation_gate`; `test_harness_repeatability_same_case_same_score`; `test_repeatability_same_inputs_same_scores` | pass |
| FR-4 | `core.py::score_case`; `aggregate`; `format_summary` | `test_blocked_stage_not_scored_as_pass`; `test_aggregate_and_summary_redacted`; `test_aggregate_counts_each_case_once_per_stage` | pass |
| FR-5 | `core.py` selection/planning/execution scorers; domain cases | `test_tool_argument_subset_and_ordered_batch`; `test_domain_constraint_case_passes`; `test_scheduling_contrast_cases_pass`; `test_relative_delay_case_omits_timezone_argument` | pass |
| FR-6 | `harness.py`; clarification + recovery fixtures (selection corrected + exhausted) | `test_clarification_suspend_resume_case`; `test_recovery_and_safe_failure_cases_pass`; `test_corpus_covers_selection_successful_correction` | pass |
| FR-7 | `core.py::_score_delivery` (exact claim sets) | `test_prohibited_claim_negative_fails_delivery`; `test_extra_delivery_claim_fails_exact_claim_scoring`; `test_internal_detail_marker_fails_delivery_scoring` | pass |
| FR-8 | `corpus-v1.json::july-20-recurring-spb-weather-accuweather` (creation + scheduled turns) | `test_july_20_regression_case`; `test_july_20_covers_scheduled_constrained_execution` | pass |

## Findings

- [x] **High** — corpus inventory coverage (no-skill, protocol exhaustion,
  refinement, preference, delayed/relative, scheduled entry, contrastive
  families) — addressed in corpus 1.1.0+ — `fixed`
- [x] **High** — `RecordedLLMApi.parse_chat_async` wrapped parse errors —
  raw `JSONDecodeError` / `ValidationError` now propagate;
  `test_recorded_llm_preserves_structured_parse_error` proves
  `StructuredOutputError` — `fixed`
- [x] **High** — `score_case` / `aggregate` blocked-observation and case-level
  counts — downstream stages score when observed; aggregation counts each
  case once per stage; summary includes case tally — `fixed`
- [x] **High** — delivery claim subset scoring / missing internal-detail
  negative — exact set equality + dedicated negatives — `fixed`
- [x] **High** — July 20 incomplete expectations — distilled fragments,
  cron/timezone, strict AccuWeather constraints, scheduled
  `include_domains`, claim boundaries asserted — `fixed`
- [x] **High** — IODA Operation→Operation (`ExecutionContextCore` /
  `MemoryCore`) — Core uses local `normalize_domains`; harness uses
  production `MemoryProvider` — `fixed`
- [x] **Medium** — harness reimplementation / `run_case` contract / salted
  `hash()` / per-turn memory — delegates via `super()`, returns
  `RoutingCaseResult`, `hashlib` IDs, case-scoped shared storage — `fixed`
- [x] **Medium** — `JsonValue` / fixture pre-checks / ordered-batch assert —
  recursive `JsonValue`, fixture validation, ordered batch expects empty
  diffs — `fixed`
- [x] **Medium** — `corpus-v1.json` / selection recovery — design Decision 7
  and plan 5.5 require a **successful** bounded correction path for
  selection; corpus 1.1.1 adds `en-selection-protocol-corrected` with
  `recovery: corrected` and ≥2 selection model responses; covered by
  `test_corpus_covers_selection_successful_correction` and gate case list
  (FR-6; plan 5.5) — `fixed`

## Follow-ups

- **Low** — `RoutingEvaluationCore.normalize_domains` duplicates
  `ExecutionContextCore.normalize_request_constraints` (IODA-safe copy);
  risk of silent drift if production host rules change.
- **Info** — `build_corpus.py` is outside the plan Files table; keep it as
  the documented regenerator or note it in close-task harvest.
- **Info** — `RecordedLLMApi` inlines JSON/Pydantic parse instead of calling
  `super().parse_chat_async`; exception contract matches production and is
  tested.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-21 | fix | 676 tests pass, but six High and two Medium contract/coverage findings remain open. |
| 2026-07-21 | fix | Re-review: prior High/Medium items fixed; 694 tests pass; one Medium FR-6 selection successful-correction corpus gap remains. |
| 2026-07-21 | pass-with-follow-ups | FR-6 selection `recovery: corrected` closed (`en-selection-protocol-corrected`, corpus 1.1.1, 26 cases); 696 tests pass; only Low/Info follow-ups remain. |
