---
id: TASK-021
doc: review
updated: 2026-07-22
verdict: pass-with-follow-ups
pytest: pass
---

# TASK-021: stage telemetry and live eval runner — Review

← [[backlog/TASK-021-stage-telemetry-and-live-eval-runner/task|Back to task]] | [[backlog/TASK-021-stage-telemetry-and-live-eval-runner/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

~32 paths vs plan Files & artifacts: new evaluation modules
(`telemetry_core`, `prompt_identity_core`, `live_core`, `live_fakes`,
`live_report_provider`, `live_evaluation`, `live_runner`, `observation`),
production edits (`mind`, `agent`, `cognition`, `language`, delivery/react
constants), tests (`test_routing_telemetry`, `test_prompt_identity`,
`test_live_routing_evaluation` + harness/language tweaks), docs
(`agent/AGENTS.md`), `.gitignore`, `implementation-notes.md`. Extra:
`tests/fakes.py` / `tests/test_agent.py` `model_name` stubs (needed by
diagnostics). No planned production path missing; no out-of-scope PR/CI live
gating. Re-review after Medium findings from earlier gate.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `RoutingTelemetryCore`; emit sites in `CognitionProvider`, `Mind`, `Agent` | `tests/test_routing_telemetry.py` — success, corrected/exhausted, execution `failed`, delivery fail/success, privacy; bypass `not_applicable`/`rejected` | pass |
| FR-2 | `PromptIdentityCore` + prompt ID constants; `LanguageProvider.model_name`; Agent multi-prompt emit; live `prompt_sink` | `tests/test_prompt_identity.py`; telemetry multi-prompt; `test_live_evaluation_prompts_used_retains_selector_and_skill` | pass |
| FR-3 | `LiveRoutingEvaluation` + `live_runner`; `LiveRoutingEvaluationCore.live_eligibility`; `ObservingMind`/`ObservingAgent` | `test_live_eligibility_*`, `test_live_evaluation_excludes_and_filters_*`, `test_live_evaluation_runs_eligible_*`; deterministic harness still green | pass |
| FR-4 | `live_fakes.FailOnCall` + recorded tools in `LiveRoutingEvaluation._build_tools` | `test_fail_on_call_stubs_raise` | pass |
| FR-5 | `LiveRoutingEvaluationCore.build_report` + `RoutingEvaluationCore.score_case` | `test_build_report_aggregates_stage_metrics_*` | pass |
| FR-6 | `LiveEvalReport` / `LiveEvalReportProvider`; CLI summary; `prompts_used` accumulation | unique path + round-trip in `test_live_report_provider_*`; console path assert; live prompts retention | pass |
| FR-7 | `live_runner` opt-in; docs in `yoda/mind/agent/AGENTS.md`; gitignore | `test_pytest_suite_does_not_import_live_runner_*`; full pytest green without credentials | pass |

## Findings

- [x] **Medium** — `LiveRoutingEvaluation.run` `prompts_used` hard-seeded intent+delivery only — fixed via shared `prompt_sink` on `ObservingCognitionProvider` / `ObservingAgent` / `ObservingMind` + `test_live_evaluation_prompts_used_retains_selector_and_skill` — `fixed`
- [x] **Medium** — missing execution-failure telemetry test — covered by `test_agent_execution_failure_diagnostic` — `fixed`
- [ ] **Low** — `yoda/mind/evaluation/prompt_identity_core.py` — Core lazy-imports prompt material from `cognition` / `react_loop` / `delivery_core` (circular-import workaround); noted in `implementation-notes.md` as tech-debt — `open`
- [ ] **Info** — `yoda/mind/evaluation/live_fakes.py` duplicates `InMemoryStorageApi` / `RecordedToolProvider` already under `tests/routing_evaluation/fakes.py` to avoid `tests.*` imports; documented follow-up — `open`
- [ ] **Info** — `RoutingTelemetryCore.format_info` / `format_warning` share the same body; level is chosen by the caller logger — acceptable — `open`
- [ ] **Info** — resume `BYPASSED` (`detail=agent_resume`) path exists in `Mind._classify_intent` but has no dedicated telemetry assert (chat `not_applicable` / rejected covered) — `open`

## Follow-ups

- Close-task may harvest PromptIdentityCore lazy-import and live-fakes duplication tech-debt from `implementation-notes.md`.
- Optional: assert resume `outcome=bypassed` / `detail=agent_resume` in `tests/test_routing_telemetry.py`.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-07-22 | fix | pytest 723 green; Medium: live `prompts_used` incomplete; Medium: missing execution-failure telemetry test |
| 2026-07-22 | pass-with-follow-ups | pytest 725 green; prior Mediums fixed; Low/Info tech-debt only |
