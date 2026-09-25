---
id: TASK-023
doc: plan
updated: 2026-09-25
last_step: 5.2
branch: feat/TASK-023-ai-inference-profiles
---

# TASK-023: ai inference profiles — Implementation plan

← [[backlog/TASK-023-ai-inference-profiles/task|Back to task]] | [[backlog/TASK-023-ai-inference-profiles/requirements|Requirements]] | [[backlog/TASK-023-ai-inference-profiles/design|Design]]

## Overview

Replace scattered model credentials with a pure inference catalog (`inference.providers` + `inference.profiles`) that resolves each consumer's `model` id to a backend, key, and `model_name` before any HTTP client exists. Startup and the live-eval CLI then build a separate `MistralApi` or `OpenRouterApi` (and `EmbeddingsApi`) per consumer. Default text consumers point at OpenRouter `qwen/qwen3.8-27b:free`; a Mistral text profile stays so operators can retarget by editing a profile id. `OpenRouterApi` gains the same structured JSON contract cognition, the agent, and the summarizer already use on Mistral.

## Goal / Non-goals

- **Goal:** `settings.json` matches the catalog in [[task#Target settings shape (example)]]. Startup and `live_runner` fail fast on a bad profile or provider reference. Language, agent, and summarizer can use different profiles. Both `mistral` and `openrouter` satisfy `ChatBackend.parse_chat_async`. Vision image payload shape follows the resolved backend. Embeddings stay on the current OpenRouter model id, with credentials taken from the catalog.
- **Non-goals:** New backends (including Jev). Moving secrets to env vars or a secret store. Changing vision or embedding model identities. A global CLI `--provider` switch. Rate-limit or retry redesign (TASK-022). Unifying Pixazo, Tavily, or Jina credentials into `inference`. Encrypting `settings.json`.

## Context to load

Files to read before starting:

- [[backlog/TASK-023-ai-inference-profiles/requirements|requirements]] — FR-1…FR-6
- [[backlog/TASK-023-ai-inference-profiles/design|design]] — «Architecture», «Interfaces», «Data model», «System impact»
- [AGENTS.md](../../../AGENTS.md) (IODA + coding guidelines), [coding_behavior.md](../../../coding_behavior.md)
- Current call sites: `yoda/yoda_chat_bot.py` (`main`), `yoda/api/llm_api.py`, `yoda/api/openrouter_api.py`, `yoda/mind/perception/language.py`, `yoda/mind/perception/vision.py`, `yoda/mind/memory/summarizer.py`, `yoda/mind/memory/data/summarizer_settings.py`, `yoda/mind/memory/data/summary_store_settings.py`, `yoda/mind/memory/embedding.py`, `yoda/mind/evaluation/live_runner.py`, `yoda/mind/evaluation/live_evaluation.py`
- Docs to edit in stage 4: `doc/runbooks/live-routing-eval.md`, `yoda/mind/evaluation/AGENTS.md`
- `settings.json` — relocate existing keys in step 4.3; do not copy secret values into tests, commits messages, or docs

## Pre-flight

Mandatory conditions before implementation starts.
If any item below fails and cannot be satisfied immediately, do not proceed to implementation.

- [ ] `git status` — working tree is clean
- [ ] `git checkout -b feat/TASK-023-ai-inference-profiles` — standalone branch (no epic)
- [ ] `.venv` active; dependencies already installed (no new packages)
- [ ] Baseline tests green: `.venv/bin/python -m pytest`
- [ ] `settings.json` is the current file (language Mistral key, OpenRouter key on vision / embeddings). Step 4.3 relocates those values in place. Pytest does not need Redis, Chroma, Telegram, or a live LLM.

## Files & artifacts

| Path | IODA | Op | FR |
|------|------|----|----|
| `yoda/api/inference/data.py` | Data | create | FR-1, FR-2, FR-3 |
| `yoda/api/inference/catalog.py` | Core | create | FR-1, FR-2, FR-3, FR-6 |
| `yoda/api/inference/backends.py` | Integration | create | FR-3, FR-4, FR-5 |
| `yoda/api/chat_backend.py` | API | create | FR-4 |
| `yoda/api/openrouter_api.py` | API | edit | FR-4 |
| `yoda/api/llm_api.py` → `yoda/api/mistral_api.py` | API | rename | FR-4 |
| `yoda/mind/perception/language.py` | Provider | edit | FR-3, FR-4 |
| `yoda/mind/memory/summarizer.py` | Provider | edit | FR-3, FR-4 |
| `yoda/mind/memory/data/summarizer_settings.py` | Data | edit | FR-3 |
| `yoda/mind/perception/vision.py` | Provider | edit | FR-3 |
| `yoda/mind/memory/data/summary_store_settings.py` | Data | edit | FR-1, FR-3 |
| `yoda/mind/memory/embedding.py` | Provider | edit | FR-3 |
| `yoda/yoda_chat_bot.py` | Integration | edit | FR-1, FR-2, FR-3, FR-4, FR-6 |
| `yoda/mind/evaluation/live_runner.py` | Integration | edit | FR-5 |
| `yoda/mind/evaluation/live_evaluation.py` | Integration | edit | FR-4, FR-5 |
| `settings.json` | Config | edit | FR-1, FR-6 |
| `doc/runbooks/live-routing-eval.md` | Doc | edit | FR-5 |
| `yoda/mind/evaluation/AGENTS.md` | Doc | edit | FR-5 |
| `tests/test_llm_api.py` → `tests/test_mistral_api.py` | Test | rename | FR-4 |
| `tests/routing_evaluation/fakes.py` | Test | edit | FR-4 |
| `tests/test_maintenance.py` | Test | edit | FR-4 |
| `tests/test_inference_catalog.py` | Test | create | FR-2, FR-3, FR-6 |
| `tests/test_openrouter_api.py` | Test | edit | FR-4 |
| `tests/test_vision_provider.py` | Test | create | FR-3 |
| `tests/test_summarizer.py` | Test | edit | FR-3 |
| `tests/test_summary_store_core.py` | Test | edit | FR-1 |
| `tests/test_embedding_provider.py` | Test | edit | FR-3 |
| `tests/test_vector_provider.py` | Test | edit | FR-1 |
| `tests/test_live_routing_evaluation.py` | Test | edit | FR-5 |
| `tests/test_language_provider.py` | Test | edit | FR-4 |

No `__init__.py` under `yoda/api/inference/`. No Redis, Chroma, or conversation migration.

`tests/fakes.py` `FakeLLMApi` stays a duck-typed double (name unchanged). `tests/test_routing_evaluation.py` and `tests/routing_evaluation/harness.py` construct `LanguageProvider` positionally; they need edits only if the constructor argument order changes (it does not).

## Stages

### Stage 1: Inference catalog

**Goal:** `InferenceCatalogCore` validates the whole catalog and resolves consumer profile ids with no network I/O.

- [x] **1.1** Catalog load and provider/profile validation
  - Files: `yoda/api/inference/data.py`, `yoda/api/inference/catalog.py`, `tests/test_inference_catalog.py`
  - Action: Data dataclasses `ResolvedInference` and `ConfiguredInference` per [[design#API / Public contract]]. Core `InferenceCatalogCore.from_settings` validates the whole catalog (including unused entries) with the `ValueError` messages in [[design#Data model]]. Supported backends are `mistral` and `openrouter`. A Mistral provider that includes `base_url` fails. Omitted OpenRouter `base_url` becomes `https://openrouter.ai/api/v1` stored on the Core (duplicate the façade constant; do not import `OpenRouterApi`). A present `base_url` is a non-empty string with any trailing slash removed. Strip `api_key` and `model_name`; empty-after-strip uses the missing-field message. Messages name ids and never keys. TDD: happy path plus missing `inference`, empty maps, missing fields, unknown backend, Mistral `base_url`, invalid OpenRouter `base_url`, profile pointing at an unknown provider.
  - Verify: `.venv/bin/python -m pytest tests/test_inference_catalog.py -q`
  - Commit: `feat(TASK-023): 1.1 validate inference catalog`

- [x] **1.2** Resolve profile ids and the five startup consumers
  - Files: `yoda/api/inference/catalog.py`, `tests/test_inference_catalog.py`
  - Action: `resolve` raises `Unknown inference profile: '{profile_id}'` with no fallback. `resolve_configured` reads `mind.perception.language.model`, `agent.model`, `mind.memory.summarizer.model`, `mind.perception.vision.model`, and `mind.memory.summary_store.embeddings.model`. A missing selector raises `Settings missing required inference model: {dotted.path}`. Embeddings whose provider `backend` is not `openrouter` raise `Embeddings profile '{profile_id}' requires backend 'openrouter', got '{backend}'`. TDD: unknown profile; embeddings backend rejection; language and agent resolve to different `model_name` / `backend` when their profile ids differ; a fixture shaped like the task example resolves `text_qwen27_free` to OpenRouter `qwen/qwen3.8-27b:free` and `text_ministral14` to Mistral `ministral-14b-latest`. Do not load the real `settings.json` in this step.
  - Verify: `.venv/bin/python -m pytest tests/test_inference_catalog.py -q`
  - Commit: `feat(TASK-023): 1.2 resolve inference profiles`

**Checkpoint Stage 1:** `.venv/bin/python -m pytest` is green. Catalog tests do not open a socket.

---

### Stage 2: Chat façades

**Goal:** `MistralApi` and `OpenRouterApi` both satisfy `ChatBackend`. Callers that only need chat+parse are typed against the protocol.

- [x] **2.1** Rename `LLMApi` to `MistralApi`
  - Files: `yoda/api/llm_api.py` → `yoda/api/mistral_api.py`, `tests/test_llm_api.py` → `tests/test_mistral_api.py`, `tests/routing_evaluation/fakes.py`, `tests/test_maintenance.py`, every remaining `yoda.api.llm_api` / `LLMApi` import (`yoda/yoda_chat_bot.py`, `yoda/mind/perception/language.py`, `yoda/mind/memory/summarizer.py`, `yoda/mind/evaluation/live_runner.py`, `yoda/mind/evaluation/live_evaluation.py`)
  - Action: Move the module and rename the class to `MistralApi`. Chat, parse, and debug-exchange behavior stay the same (`complete_chat_via_thread` stays on `MistralApi` only). `RecordedLLMApi` keeps its class name and subclasses `MistralApi`. `tests/test_maintenance.py` forbidden-import string becomes `yoda.api.mistral_api`. Leave constructor parameter names (`llm_api`) for step 2.2. Confirm `rg` finds no `LLMApi` or `yoda.api.llm_api` outside docs that this task does not own.
  - Verify: `.venv/bin/python -m pytest tests/test_mistral_api.py tests/test_language_provider.py tests/test_summarizer.py tests/test_routing_evaluation.py tests/test_live_routing_evaluation.py tests/test_maintenance.py -q`
  - Commit: `refactor(TASK-023): 2.1 rename LLMApi to MistralApi`

- [x] **2.2** Type chat callers against `ChatBackend`
  - Files: `yoda/api/chat_backend.py`, `yoda/mind/perception/language.py`, `yoda/mind/memory/summarizer.py`, `yoda/mind/evaluation/live_evaluation.py`, `yoda/yoda_chat_bot.py`, `yoda/mind/evaluation/live_runner.py`, `tests/test_live_routing_evaluation.py`, `tests/test_language_provider.py`
  - Action: Protocol `ChatBackend` with `complete_chat_async` and `parse_chat_async` per [[design#API / Public contract]]. `LanguageProvider.__init__(self, settings: dict, chat_backend: ChatBackend)` still reads `settings["model_name"]` and still maps `JSONDecodeError` / `ValidationError` to `StructuredOutputError` with no raw content in the message. `SummarizerProvider.__init__(self, chat_backend: ChatBackend, settings: SummarizerSettings)`. `LiveRoutingEvaluation.__init__(..., chat_backend: ChatBackend, model_name: str, ...)`. Rename the stored attribute off `LLMApi`. Update keyword call sites (`llm_api=` → `chat_backend=`). Positional `LanguageProvider` / `SummarizerProvider` tests stay valid. `MistralApi` is not imported by `LanguageProvider`, `SummarizerProvider`, or `LiveRoutingEvaluation`. Existing structured-error tests stay the contract check; do not weaken assertions.
  - Verify: `.venv/bin/python -m pytest tests/test_language_provider.py tests/test_summarizer.py tests/test_live_routing_evaluation.py tests/test_routing_evaluation.py -q`
  - Commit: `refactor(TASK-023): 2.2 type chat callers as ChatBackend`

- [x] **2.3** OpenRouter structured parse
  - Files: `yoda/api/openrouter_api.py`, `tests/test_openrouter_api.py`
  - Action: `OpenRouterApi.parse_chat_async` posts `response_format: {"type": "json_object"}`, `json.loads` the string content, and `model_validate`s — same contract as `MistralApi.parse_chat_async` ([[design#Decision 2]]). `JSONDecodeError` and `ValidationError` propagate. A non-string `content` raises `ValueError("OpenRouter structured content is not a string")` and is not wrapped as `StructuredOutputError` by this method. Debug logs may include a content prefix; exception messages must not. Reuse the existing httpx monkeypatch style in `tests/test_openrouter_api.py`. TDD: success payload is validated into a tiny pydantic model and the posted body contains `json_object`; invalid JSON raises `JSONDecodeError`; non-string content raises the `ValueError` above. No live network.
  - Verify: `.venv/bin/python -m pytest tests/test_openrouter_api.py tests/test_language_provider.py -q`
  - Commit: `feat(TASK-023): 2.3 parse structured output on OpenRouter`

**Checkpoint Stage 2:** `.venv/bin/python -m pytest` is green.

---

### Stage 3: Consumer settings

**Goal:** Providers take a resolved `model_name` (and vision `backend`). They no longer read credentials or fall back across consumers. `main()` still uses the old settings paths until stage 4; pytest does not execute `main()`.

- [x] **3.1** Drop summarizer settings fallback
  - Files: `yoda/mind/memory/data/summarizer_settings.py`, `tests/test_summarizer.py`
  - Action: Delete `SummarizerSettings.from_settings`. The dataclass stays `model_name: str` only — the resolved model id, not a profile id ([[design#Decision 4]]). Remove the tests that expect `chat_compression.summarizer.model_name` or a fallback to `language.model_name`. Keep `SummarizerProvider` tests that construct `SummarizerSettings(model_name=...)` directly.
  - Verify: `.venv/bin/python -m pytest tests/test_summarizer.py -q`
  - Commit: `feat(TASK-023): 3.1 require a resolved summarizer model`

- [x] **3.2** Vision image shape follows the resolved backend
  - Files: `yoda/mind/perception/vision.py`, `tests/test_vision_provider.py`
  - Action: `VisionProvider.__init__(self, settings: dict, chat_backend: VisionChatBackend, backend: BackendName)`. `backend` is required (no default, do not read `settings["provider"]`). `settings["model_name"]` remains the resolved model id. `_image_part`: `openrouter` uses `{"type": "image_url", "image_url": {"url": data_url}}`; `mistral` uses `image_url` as a string. TDD with a temp image file and a fake `complete_chat_async` that records `messages`: both backends, and a missing `backend` argument fails at construction.
  - Verify: `.venv/bin/python -m pytest tests/test_vision_provider.py -q`
  - Commit: `feat(TASK-023): 3.2 select vision image shape from backend`

- [x] **3.3** Embeddings settings hold only the resolved model name
  - Files: `yoda/mind/memory/data/summary_store_settings.py`, `yoda/mind/memory/embedding.py`, `tests/test_summary_store_core.py`, `tests/test_embedding_provider.py`, `tests/test_vector_provider.py`
  - Action: `EmbeddingsSettings` is `model_name` only. `SummaryStoreSettings` keeps `persist_directory` and `collection_prefix` and drops the embeddings field; `from_dict` does not require or read `embeddings` (a leftover block is ignored, same as `search` / `document_encryption`). `EmbeddingProvider` still validates `settings.model_name` against `MODEL_DIMENSIONS` and does not see an API key. Update fixtures that pass `openrouter_api_key` or `SummaryStoreSettings.embeddings`. Unknown model still fails at `EmbeddingProvider` init.
  - Verify: `.venv/bin/python -m pytest tests/test_summary_store_core.py tests/test_embedding_provider.py tests/test_vector_provider.py -q`
  - Commit: `feat(TASK-023): 3.3 drop embeddings credentials from store settings`

**Checkpoint Stage 3:** `.venv/bin/python -m pytest` is green. Do not start the bot; `main()` is updated in stage 4.

---

### Stage 4: Wiring, settings, live eval

**Goal:** Startup and live eval build façades from the catalog. Committed settings match the task example. Docs stop mentioning `llm.api_key` and `agent.model_name`.

- [x] **4.1** Backend factories
  - Files: `yoda/api/inference/backends.py`, `tests/test_inference_catalog.py`
  - Action: Integration functions `build_chat_backend` and `build_embeddings_api` per [[design#API / Public contract]]. `mistral` → `MistralApi(api_key, debug_log_dir=debug_log_dir)`. `openrouter` → `OpenRouterApi(api_key, base_url=resolved.base_url)`. Unknown backend raises (catalog already rejects it; the factory still fails fast). `build_embeddings_api` repeats the OpenRouter-only check with the same message as `resolve_configured`, then returns `EmbeddingsApi`. Debug exchange files stay Mistral-only. TDD: factory returns the matching class for each backend; embeddings factory rejects `mistral`. Constructing `MistralApi` must not perform HTTP (existing client init).
  - Verify: `.venv/bin/python -m pytest tests/test_inference_catalog.py -q`
  - Commit: `feat(TASK-023): 4.1 build chat and embeddings façades`

- [x] **4.2** Wire startup from `resolve_configured`
  - Files: `yoda/yoda_chat_bot.py`
  - Action: `main` calls `InferenceCatalogCore.resolve_configured` once after the settings JSON loads. On catalog `ValueError`, let it propagate (fail fast, no fallback). Build a separate client per consumer, even when profile ids match: language+cognition share one `LanguageProvider({"model_name": language.model_name}, chat_backend)`; agent gets its own backend and provider; summarizer gets its own backend and `SummarizerSettings(model_name=summarizer.model_name)`; vision gets `build_chat_backend(vision)` plus `backend=vision.backend` and `{"model_name": vision.model_name}`; embeddings gets `build_embeddings_api` plus `EmbeddingsSettings(model_name=embeddings.model_name)`. Pass `debug_log_dir` only into chat factories (Mistral debug logs). Stop reading `language.api_key`, `vision.api_key`, `vision.provider`, `agent.model_name`, and `embeddings.openrouter_api_key`. Leave embodiment, agent tool keys, compression, maintenance, and emotions as they are. This step does not yet rewrite `settings.json` — the process will not boot until 4.3.
  - Verify: `.venv/bin/python -m pytest tests/test_mind_pipelines.py tests/test_maintenance.py -q` and `rg "api_key|model_name|from_settings" yoda/yoda_chat_bot.py` shows no consumer credential reads (tool keys such as `tavily_api_key` remain).
  - Commit: `feat(TASK-023): 4.2 wire startup through the inference catalog`

- [x] **4.3** Commit the catalog in `settings.json`
  - Files: `settings.json`, `tests/test_inference_catalog.py`
  - Action: Reshape `settings.json` to [[task#Target settings shape (example)]] and [[design#Committed settings]]. Move the current `mind.perception.language.api_key` onto `inference.providers.mistral` (Decision 6). Move the current OpenRouter key (vision / dead `perception.openrouter` / embeddings — same value) onto `inference.providers.openrouter` with `base_url` `https://openrouter.ai/api/v1`. Profile ids: `text_qwen27_free`, `text_ministral14`, `vision_qwen_vl`, `embed_openai_small` with the model names in the design data model. Consumer `model` ids: language, agent, and summarizer → `text_qwen27_free`; vision → `vision_qwen_vl`; embeddings → `embed_openai_small`. Keep `summary_store.persist_directory` and `collection_prefix`. Delete obsolete fields listed in FR-1. Do not print or assert secret values. TDD: load the repo `settings.json`, `resolve_configured`, assert backends and `model_name`s for the five consumers (text three are OpenRouter `qwen/qwen3.8-27b:free`; vision and embeddings keep today's model ids), and assert the obsolete keys are absent.
  - Verify: `.venv/bin/python -m pytest tests/test_inference_catalog.py -q`
  - Commit: `feat(TASK-023): 4.3 move settings onto inference profiles`

- [x] **4.4** Live eval resolves `agent.model`
  - Files: `yoda/mind/evaluation/live_runner.py`, `tests/test_live_routing_evaluation.py`
  - Action: Load JSON, `InferenceCatalogCore.from_settings`, `resolve(agent["model"])`, `build_chat_backend`. `KeyError` or catalog `ValueError` becomes `SystemExit` with that message before `LiveRoutingEvaluation.run`. Do not require language, summarizer, vision, or embeddings selectors. Drop `llm.api_key` and `agent.model_name`. TDD in `tests/test_live_routing_evaluation.py` (this file may import `live_runner`; other test modules must not): missing `agent.model` and an unknown profile each `SystemExit` before a corpus case; a settings file with only `inference` + `agent.model` builds the evaluation (monkeypatch `run` so no network).
  - Verify: `.venv/bin/python -m pytest tests/test_live_routing_evaluation.py -q`
  - Commit: `feat(TASK-023): 4.4 resolve live eval from agent.model`

- [x] **4.5** Document the live-eval settings contract
  - Files: `doc/runbooks/live-routing-eval.md`, `yoda/mind/evaluation/AGENTS.md`
  - Action: Runbook prerequisites are `inference` (providers + profiles) and `agent.model`. Remove `agent.model_name` and `llm.api_key`. Side-effect sentence: only the resolved chat façade (`MistralApi` or `OpenRouterApi`) may network. In `yoda/mind/evaluation/AGENTS.md`, state the same side-effect boundary next to the live CLI pointer. No new runbook sections beyond that contract.
  - Verify: `rg "llm.api_key|agent.model_name" doc/runbooks/live-routing-eval.md yoda/mind/evaluation/AGENTS.md` returns no matches, and both files name `agent.model`.
  - Commit: `docs(TASK-023): 4.5 document inference catalog for live eval`

**Checkpoint Stage 4:** `.venv/bin/python -m pytest` is green. `InferenceCatalogCore.resolve_configured` on the repo `settings.json` returns the five default profiles without raising.

---

### Stage 5: Test sweep & coverage

- [x] **5.1** Close remaining FR gaps
  - Files: `tests/test_inference_catalog.py`, `tests/test_language_provider.py`, `tests/test_openrouter_api.py`, `tests/test_live_routing_evaluation.py`
  - Action: Confirm the suite already covers every acceptance criterion below; add only the missing case. FR-2: missing profile, missing provider, unknown backend, missing required field (no network). FR-3: language vs agent profile ids differ and resolve independently; summarizer has no language fallback (no `from_settings`). FR-4: OpenRouter parse success and invalid JSON; `StructuredOutputError` string is exactly `StructuredOutputError` when the fake backend raises `JSONDecodeError`. FR-5: bad catalog exits before `run`. FR-6: committed defaults for language, agent, and summarizer are `text_qwen27_free` / `qwen/qwen3.8-27b:free`; `text_ministral14` still resolves to Mistral `ministral-14b-latest`. Grep the tree for `yoda.api.llm_api`, `LLMApi`, and `SummarizerSettings.from_settings` — production and tests must be clean (historical backlog docs are out of scope).
  - Verify: `.venv/bin/python -m pytest`
  - Commit: `test(TASK-023): 5.1 close inference profile coverage`

- [x] **5.2** Manual acceptance check
  - FR-1: repo `settings.json` has non-empty `inference.providers` and `inference.profiles`; obsolete keys from FR-1 are absent (`language.api_key`, `language.model_name`, top-level `llm`, `perception.openrouter`, `vision.provider` / `api_key` / `model_name`, `embeddings.model_name` / `openrouter_api_key`, `agent.model_name`).
  - FR-2: a one-off `resolve("no-such-profile")` against the repo settings raises `Unknown inference profile: 'no-such-profile'`.
  - FR-3: `resolve_configured` on the repo file yields five `ResolvedInference` values; swapping only `agent.model` to `text_ministral14` in a copy (do not commit the swap) changes the agent backend to `mistral` and leaves language on OpenRouter.
  - FR-4: `tests/test_openrouter_api.py` and `tests/test_language_provider.py` already green from 5.1. No live OpenRouter call required.
  - FR-5: `live_runner` with a temp settings file that omits `agent.model` exits before any corpus case; runbook prerequisites name `inference` and `agent.model`.
  - FR-6: language, agent, and summarizer `model` ids are `text_qwen27_free`; `text_ministral14` remains in `inference.profiles`; vision model name is `qwen/qwen3-vl-235b-a22b-thinking`; embeddings model name is `openai/text-embedding-3-small`.

**Checkpoint Stage 5:** `.venv/bin/python -m pytest` is green, and the 5.2 checks are recorded in the step checkbox only after they pass.

## Stage dependencies

```mermaid
graph LR
    S1[Stage 1 catalog] --> S2[Stage 2 chat façades]
    S2 --> S3[Stage 3 consumer settings]
    S3 --> S4[Stage 4 wiring and settings]
    S4 --> S5[Stage 5 test sweep]
```

## FR coverage (traceability)

| FR | Steps | Verification |
|----|-------|--------------|
| FR-1 | 1.1, 4.3, 5.2 | unit `tests/test_inference_catalog.py`; manual: obsolete keys absent from `settings.json` |
| FR-2 | 1.1, 1.2, 5.2 | unit `tests/test_inference_catalog.py`; manual: unknown profile id names itself |
| FR-3 | 1.2, 3.1, 3.2, 3.3, 4.2, 5.1 | unit catalog (distinct language vs agent), `tests/test_summarizer.py`, `tests/test_vision_provider.py`, `tests/test_embedding_provider.py` |
| FR-4 | 2.1, 2.2, 2.3, 5.1 | unit `tests/test_mistral_api.py`, `tests/test_openrouter_api.py`, `tests/test_language_provider.py` |
| FR-5 | 4.4, 4.5, 5.2 | unit `tests/test_live_routing_evaluation.py`; manual: runbook + temp settings `SystemExit` |
| FR-6 | 1.2, 4.3, 5.2 | unit catalog against repo `settings.json`; manual: three text consumers on `text_qwen27_free`, Mistral profile still present |

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Free-tier `qwen/qwen3.8-27b:free` rejects `response_format: json_object` at runtime | Medium | High — cognition, agent, and summarizer fail on the new default | Step 2.3 locks the request shape in unit tests. Operator rollback is editing `language` / `agent` / `summarizer` `model` to `text_ministral14` (FR-6). Do not add retries here (TASK-022). |
| Rename misses a `LLMApi` import and breaks a later stage | Medium | Medium — red suite | Step 2.1 greps the tree and runs the modules that import the façade before any protocol edits. |
| Step 4.3 copies the live-eval `llm.api_key` onto the Mistral provider | Low | High — Mistral rollback uses a key that never served chat | Decision 6: move `mind.perception.language.api_key` only. Do not assert key strings in tests. |
| Stages 3–4 leave `main()` unable to boot until 4.3 lands | High during the branch | Low for CI — pytest never calls `main()` | Do not start the bot before the stage 4 checkpoint. Steps stay in order. |

## Rollback

- Code and `settings.json`: `git revert` the branch commits, or restore `settings.json` from the parent revision. No Redis or Chroma keys change.
- Operator rollback without reverting the catalog: set `mind.perception.language.model`, `agent.model`, and/or `mind.memory.summarizer.model` to `text_ministral14`.

## Definition of Done

- [x] All plan steps checked
- [x] All acceptance criteria from requirements.md pass
- [x] Full suite green: `.venv/bin/python -m pytest`
- [x] IODA + coding guidelines (AGENTS.md) respected — catalog Core has no HTTP imports; only `backends.py` constructs clients
- [x] `settings.json` matches the task catalog; obsolete credential fields are gone; secrets were not copied into tests or docs
- [x] `doc/runbooks/live-routing-eval.md` and `yoda/mind/evaluation/AGENTS.md` describe `inference` + `agent.model` and the resolved chat façade
- [ ] `review.md`: verdict `pass` or `pass-with-follow-ups`
- [ ] `task.md`: `status: done`, `updated: <today>`
- [ ] `design.md` updated if execution diverged from this plan (Decision 1 stays an ADR candidate; do not write an ADR in this task)
