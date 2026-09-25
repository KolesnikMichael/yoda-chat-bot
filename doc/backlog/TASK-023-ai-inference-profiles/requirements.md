---
id: TASK-023
doc: requirements
updated: 2026-09-25
---

# TASK-023: ai inference profiles — Requirements

← [[backlog/TASK-023-ai-inference-profiles/task|Back to task]]

## Context

Mistral free-tier model quality degraded after policy changes; production text calls currently go through a Mistral-only [`LLMApi`](../../../yoda/api/llm_api.py) wired from `mind.perception.language.api_key` + `model_name`, with a separate `agent.model_name` override and a largely unused top-level `llm.api_key` consumed only by the live routing eval runner. This task renames that façade to `MistralApi` in `yoda/api/mistral_api.py`. Vision already supports OpenRouter via a local `provider` flag; embeddings and a dead `mind.perception.openrouter` block duplicate the same OpenRouter key. Operators cannot point language, agent, summarizer, vision, and embeddings at different backend+model pairs without code or copy-paste credential sprawl.

This task introduces a shared **inference catalog** in `settings.json` (`providers` + `profiles`) and makes every model consumer select a profile by id. Default text profiles use OpenRouter `qwen/qwen3.8-27b:free`; a Mistral text profile remains for rollback and A/B experiments. Stakeholders: operators (switch models without redeploying logic), chat/agent quality, and downstream [[TASK-022-live-agent-eval-improvements/task|TASK-022]] (must stop depending on the old `llm.api_key` / `agent.model_name` contract).

## Functional requirements

### FR-1: Inference catalog in settings

`settings.json` must expose a top-level `inference` section with two maps: **providers** (transport + credentials) and **profiles** (provider reference + model id).

**Acceptance criteria:**
- [ ] `inference.providers` is a non-empty object; each entry has a string id and required fields `backend` and `api_key`.
- [ ] Supported `backend` values for this task are `mistral` and `openrouter`; unknown backends fail fast at resolve/startup.
- [ ] OpenRouter providers may include `base_url`; when omitted, the existing OpenRouter default base URL is used.
- [ ] `inference.profiles` is a non-empty object; each entry has required `provider` (id into `providers`) and `model_name` (string).
- [ ] Repo `settings.json` matches the catalog shape in [[backlog/TASK-023-ai-inference-profiles/task|task]] (example JSON), with production text defaults pointing at OpenRouter `qwen/qwen3.8-27b:free` and a Mistral text profile (`ministral-14b-latest` or equivalent) present for experiments.
- [ ] Obsolete fields are absent from committed `settings.json`: `mind.perception.language.api_key`, `mind.perception.language.model_name`, top-level `llm`, `mind.perception.openrouter`, `vision.provider` / `vision.api_key` / `vision.model_name`, `embeddings.model_name` / `embeddings.openrouter_api_key`, `agent.model_name`.

### FR-2: Resolve profile → provider + model

Startup (and live eval) must resolve a consumer's `model` id to a concrete backend, credentials, and `model_name` with fail-fast validation.

**Acceptance criteria:**
- [ ] Resolving an unknown profile id raises a clear error naming the missing id (no silent fallback to another profile).
- [ ] Resolving a profile whose `provider` is missing from `inference.providers` raises a clear error naming both profile and provider ids.
- [ ] Missing required provider/profile fields fail fast before any network call.
- [ ] Unit tests cover happy path and missing profile / missing provider / unknown backend without live network.

### FR-3: Per-consumer `model` selection

Each in-scope consumer selects its inference profile independently via a `model` field holding a profile id.

**Acceptance criteria:**
- [ ] `mind.perception.language.model` drives chat reply and cognition structured calls.
- [ ] `agent.model` drives the agent `LanguageProvider` (selection/execution); it may differ from `language.model`.
- [ ] `mind.memory.summarizer.model` is required and drives summarisation; there is no fallback to the language profile.
- [ ] `mind.perception.vision.model` drives vision describe calls; image payload shape follows the resolved provider `backend` (OpenRouter vs Mistral), not a separate `vision.provider` setting.
- [ ] `mind.memory.summary_store.embeddings.model` drives embeddings model name and credentials via the resolved OpenRouter-capable provider.
- [ ] Changing only a consumer's `model` id (to another valid profile) is sufficient to retarget that consumer; no code change required.
- [ ] Wiring / loader tests (or equivalent) assert independent language vs agent profile resolution when ids differ.

### FR-4: Chat backends honour structured output

Text consumers that today call `parse_chat_async` / structured JSON must work when the selected profile's backend is OpenRouter as well as Mistral.

**Acceptance criteria:**
- [ ] OpenRouter chat façade supports structured/json object completion equivalent to `MistralApi.parse_chat_async` (cognition, agent phases, summarizer).
- [ ] The Mistral chat façade is `MistralApi` in `yoda/api/mistral_api.py`, renamed from `LLMApi` / `yoda/api/llm_api.py`. Call sites and tests import the new module.
- [ ] `LanguageProvider` (or its chat backend boundary) is not hard-wired to the Mistral client type alone; both backends satisfy the chat+parse contract used in production.
- [ ] Unit tests cover OpenRouter structured parse success and invalid-JSON failure without live network.
- [ ] Existing LanguageProvider structured-error contract (`StructuredOutputError` without raw content in the message) remains intact when the backend is OpenRouter.

### FR-5: Live routing eval uses the catalog

The on-demand live routing eval runner must obtain model + credentials from the inference catalog via `agent.model`, not from `llm.api_key` + `agent.model_name`.

**Acceptance criteria:**
- [ ] [`live_runner`](../../../yoda/mind/evaluation/live_runner.py) resolves `agent.model` → profile → provider and constructs the matching chat backend.
- [ ] Missing `agent.model` or an invalid catalog reference fails before any corpus case is attempted.
- [ ] [[runbooks/live-routing-eval]] documents the new prerequisites (`inference` + `agent.model`) instead of `agent.model_name` and `llm.api_key`.

### FR-6: Operator defaults and rollback without code changes

Committed defaults must prefer OpenRouter for the text stack while keeping a one-setting-change rollback path to Mistral.

**Acceptance criteria:**
- [ ] Default `language`, `agent`, and `summarizer` profile ids in repo `settings.json` resolve to OpenRouter `qwen/qwen3.8-27b:free`.
- [ ] A Mistral text profile remains in `inference.profiles` so operators can point any of those three consumers at it by editing only the `model` id.
- [ ] Vision and embeddings defaults preserve today's model identities, relocated into profiles (no intentional model upgrade/downgrade in this task).

## Constraints & assumptions

- **Constraint:** IODA — resolve/validation logic stays free of Provider/Portal/network side effects; HTTP remains in API façades (`MistralApi`, `OpenRouterApi`, `EmbeddingsApi`). The inference catalog lives under `yoda/api/inference/` and does not perform network I/O.
- **Constraint:** Fail fast on config errors; no lenient fallback to a “default” profile or to the language model for summarizer.
- **Constraint:** Do not invent a new backend client (e.g. Jev); only `mistral` and `openrouter` in this task.
- **Assumption:** Relocating summarizer config to `mind.memory.summarizer.model` (and dropping any `chat_compression.summarizer.model_name` fallback) is acceptable; nothing in Redis/Chroma persists the old summarizer settings path.
- **Assumption:** Embeddings remain OpenRouter-HTTP compatible; an embeddings profile whose provider `backend` is not usable for embeddings fails fast at wiring (design specifies the exact check).
- **Assumption:** No conversation/Redis schema migration — this is settings + wiring only.
- **Assumption:** [[TASK-022-live-agent-eval-improvements/task|TASK-022]] will build on the post-TASK-023 live-eval settings contract; this task only replaces the broken credential path, not the full dedicated `evals` block.

## Out of scope

- Implementing a Jev (or other) backend client
- Moving API keys to environment variables / secret managers
- Changing vision or embedding model ids beyond catalog relocation
- Global CLI `--provider` switch
- Rate-limit / retry redesign for live eval or production (TASK-022 and related)
- Unifying Pixazo / Tavily / Jina credentials into `inference`
- Encrypting `settings.json` secrets
