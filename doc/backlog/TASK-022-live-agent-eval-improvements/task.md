---
id: TASK-022
epic:
title: "live agent eval improvements"
status: todo
priority: medium
size: M
created: 2026-07-22
updated: 2026-07-22
tags:
  - evaluation
  - live-eval
  - settings
---

# TASK-022: live agent eval improvements

## Description

Improve the on-demand live routing evaluation runner delivered by TASK-021: dedicated `evals` configuration in `settings.json`, a human-readable report alongside the existing JSON artifact, configurable LLM pacing and retries for corpus runs, and a new default report directory (`evals/live_routing`). Operators should be able to run and review live evals without parsing JSON or hand-wiring credentials from unrelated settings blocks.

## Context (as-built baseline)

TASK-021 closed with a working live runner. Relevant current behavior:

| Concern | Current behavior |
|---------|------------------|
| Entry | `python -m yoda.mind.evaluation.live_runner` |
| Credentials / model | `settings.json`: `agent.model_name` + `llm.api_key` (CLI `--settings`) |
| Report dir default | `artifacts/live_routing_eval` (`DEFAULT_REPORT_DIR` in `live_evaluation.py`; gitignored) |
| Report format | Privacy-safe JSON only (`LiveEvalReport` via `LiveEvalReportProvider`) |
| Console | Short summary + artifact path (`LiveRoutingEvaluationCore.format_console_summary`) |
| Side effects | Only `LLMApi` may network; other boundaries fail-closed (`live_fakes.py`) |
| CI | Deterministic corpus (TASK-020) stays PR-gating; live runner remains opt-in |

Key code paths (read before requirements/design):

- `yoda/mind/evaluation/live_runner.py`
- `yoda/mind/evaluation/live_evaluation.py`
- `yoda/mind/evaluation/live_report_provider.py`
- `yoda/mind/evaluation/live_core.py`
- `yoda/mind/agent/AGENTS.md` (live-runner docs)

Provenance: [[backlog/EPIC-002-agent-routing-reliability/follow-up|EPIC-002 follow-ups]] items F-4…F-7 (post-close product asks).

## Scope boundary

**In scope:**

1. **Dedicated `evals` settings block (F-7)** — Top-level `evals` section in `settings.json` with everything needed to run live routing eval (model, credentials, report path, pacing, retries, corpus path). Typed Data loader with fail-fast validation. `live_runner` reads this section; existing CLI flags remain overrides where they exist today (`--case`, `--corpus`, `--report-dir`, `--settings`).

2. **Human-readable report (F-4)** — Each successful write produces JSON **and** a readable sibling artifact (Markdown or plain text) in the same report directory, derived from the same `LiveEvalReport` (single source of truth). Filename pairing must be obvious (same run id / stem). Minimum contents: run id, status, model id, corpus version, timestamps; attempted / passed / failed / excluded / incomplete counts; per-stage pass rates; exclusion list (case id + reason); failed / incomplete case ids (no user utterance text); path to JSON sibling; distinct `prompts_used` (id + hash only).

3. **LLM pacing and retries (F-5)** — Configurable `rate_limit` (unit to be defined in requirements: e.g. max requests per minute or minimum delay between calls) and `retry_count` for retryable provider errors (429 / transient network). Fail fast on auth / non-retryable errors. Retries that exhaust must not count as stage passes; operational errors stay in existing `OperationalErrorCategory` / incomplete case handling.

4. **Default report path (F-6)** — Default report directory becomes `evals/live_routing` (code and/or settings default). Update `.gitignore` for generated reports under that tree. CLI `--report-dir` still overrides. Migrate docs and code references from `artifacts/live_routing_eval`.

**Out of scope:**

- Making live evaluation PR-blocking or defining release pass thresholds.
- Changing corpus expectations to chase model variance.
- Calling real Telegram / Tavily / Redis / Chroma / scheduler from the live runner.
- HTML dashboards, remote storage upload, PR comments.
- Changing production bot chat path rate limits.
- Unbounded backoff; making live eval CI-blocking.
- Migrating historical local artifacts under the old default path.
- Remote config services; encrypting keys beyond existing local `settings.json` practice; CI secrets wiring for mandatory live runs.

## Decisions for requirements phase

Resolve explicitly when writing FRs (do not leave implicit):

- Whether `evals.live_routing.api_key` / `model_name` are **required** or may fall back to `llm` / `agent` with documented precedence (product prefers fail-fast dedicated keys for eval isolation).
- **`rate_limit` unit and semantics** — define precisely (requests per minute vs minimum inter-call delay, defaults).
- **Readable report format** — Markdown vs plain text (either acceptable if privacy rules hold).

**Constraints (carry into requirements):**

- ADR-000: reports and logs must not store user-message replicas, prompt bodies, raw model responses, or credentials.
- IODA: apply pacing/retry policy at the live evaluation / LanguageProvider boundary used by the runner, not scattered across stage Integrations; Core for pure retry/eligibility decisions if needed; Provider/API for actual waits and HTTP.

## Related documents

- [[backlog/TASK-022-live-agent-eval-improvements/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/TASK-022-live-agent-eval-improvements/design|design]] — architectural solution
- [[backlog/TASK-022-live-agent-eval-improvements/plan|plan]] — implementation plan
- [[backlog/TASK-022-live-agent-eval-improvements/review|review]] — plan-compliance gate (verdict + findings)
- [[backlog/TASK-021-stage-telemetry-and-live-eval-runner/task|TASK-021]] — as-built live runner and report pipeline
- [[backlog/EPIC-002-agent-routing-reliability/follow-up|EPIC-002 follow-ups]] — source items F-4…F-7

## Dependencies

- Depends on: [[TASK-021-stage-telemetry-and-live-eval-runner/task|TASK-021]]
- Blocks: none

## Notes

Standalone task (not an EPIC-002 member; epic is done). Default branch: use `main` or a new feature branch as preferred — EPIC-002 shared branch is no longer required.
