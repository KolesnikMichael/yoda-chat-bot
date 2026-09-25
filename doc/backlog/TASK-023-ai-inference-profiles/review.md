---
id: TASK-023
doc: review
updated: 2026-09-25
verdict: pass-with-follow-ups
pytest: pass
---

# TASK-023: ai inference profiles — Review

← [[backlog/TASK-023-ai-inference-profiles/task|Back to task]] | [[backlog/TASK-023-ai-inference-profiles/plan|Plan]]

Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).

## Scope

Branch `feat/TASK-023-ai-inference-profiles`. All plan stages are checked. Working tree: staged renames `yoda/api/llm_api.py` → `yoda/api/mistral_api.py` and `tests/test_llm_api.py` → `tests/test_mistral_api.py`; 21 modified paths (catalog wiring, chat façades, consumer settings, live eval, runbook); untracked `yoda/api/chat_backend.py`, `yoda/api/inference/{data,catalog,backends}.py`, `tests/test_inference_catalog.py`, `tests/test_vision_provider.py`. Local `settings.json` (gitignored) matches the catalog. `yoda/mind/memory/embedding.py` was listed in the plan and needed no edit: it already takes `EmbeddingsSettings.model_name` only.

IODA holds: `InferenceCatalogCore` depends only on Data and does no I/O; only `backends.py` constructs `MistralApi` / `OpenRouterApi` / `EmbeddingsApi`; providers take a resolved `model_name` and a chat protocol, not profile ids or keys. Non-goals (new backends, secret store, CLI `--provider`, retry redesign) are absent.

## FR matrix

| FR | Code | Test | Status |
|----|------|------|--------|
| FR-1 | `InferenceCatalogCore.from_settings`; repo `settings.json` `inference.providers` / `inference.profiles`; obsolete credential fields removed | `test_from_settings_accepts_a_valid_catalog`, `test_from_settings_rejects_missing_or_non_object_inference`, `test_from_settings_rejects_empty_or_non_object_maps`, `test_from_settings_rejects_unknown_backend_without_leaking_the_key`, `test_repo_settings_resolve_the_committed_profiles` | pass |
| FR-2 | `resolve` / `from_settings` fail-fast messages (unknown profile, unknown provider, missing field, unknown backend) before any client exists | `test_resolve_unknown_profile_names_the_id`, `test_from_settings_rejects_unknown_provider_on_an_unused_profile`, `test_from_settings_rejects_missing_fields`, `test_from_settings_rejects_unknown_backend_without_leaking_the_key` | pass |
| FR-3 | `main` builds one façade per consumer from `resolve_configured`; cognition shares the language provider; agent gets its own; `SummarizerSettings.from_settings` removed; `VisionProvider` image shape follows `backend`; embeddings are `model_name` only and OpenRouter-only | `test_language_and_agent_resolve_independently`, `test_resolve_configured_requires_each_consumer_model`, `test_resolve_configured_rejects_non_openrouter_embeddings`, `test_vision_image_shape_follows_backend`, `test_vision_provider_requires_backend`, `test_embedding_provider_unknown_model_raises`, `test_summary_store_settings_from_dict_valid` | pass |
| FR-4 | `MistralApi` in `yoda/api/mistral_api.py`; `ChatBackend`; `OpenRouterApi.parse_chat_async` posts `json_object` and validates; `LanguageProvider` maps `JSONDecodeError` / `ValidationError` to `StructuredOutputError` | `test_openrouter_parse_chat_validates_json_object`, `test_openrouter_parse_chat_invalid_json_raises`, `test_openrouter_parse_chat_non_string_content_raises`, `test_parse_structured_raises_StructuredOutputError_on_bad_json`, `test_build_chat_backend_returns_the_matching_facade` | pass |
| FR-5 | `live_runner._load_agent_chat` resolves `agent.model` and exits on `KeyError` / catalog `ValueError` before `LiveRoutingEvaluation`; runbook prerequisites are `inference` + `agent.model` | `test_live_runner_missing_agent_model_exits_before_run`, `test_live_runner_unknown_profile_exits_before_run`, `test_live_runner_builds_evaluation_from_agent_model_only` | pass |
| FR-6 | Language, agent, and summarizer are `text_qwen27_free` → OpenRouter `qwen/qwen3.8-27b:free`; `text_ministral14` remains Mistral `ministral-14b-latest`; vision and embeddings keep prior model ids | `test_repo_settings_resolve_the_committed_profiles`, `test_example_profiles_resolve_to_qwen_and_ministral`, `test_language_and_agent_resolve_independently` | pass |

## Findings

- [x] **Low** — `yoda/mind/evaluation/AGENTS.md` — the step 4.5 side-effect sentence is inserted inside the "Where to look" table (after the live-CLI row), so the production-telemetry and epic rows are no longer table rows — fixed at close

## Follow-ups

- Move the live-eval sentence in `yoda/mind/evaluation/AGENTS.md` to after the "Where to look" table so the telemetry and epic rows stay in the table. Done at close. Required text (`agent.model`, `inference`, `MistralApi` or `OpenRouterApi`) stays; `doc/runbooks/live-routing-eval.md` is intact.

## History

| Date | Verdict | Note |
|------|---------|------|
| 2026-09-25 | pass-with-follow-ups | 767 passed. Catalog, façades, wiring, and live-eval match the plan. One open Low: broken markdown table in evaluation AGENTS.md. |
