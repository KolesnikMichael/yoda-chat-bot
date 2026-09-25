---
id: TASK-023
epic:
title: "ai inference profiles"
status: done
priority: high
size: M
created: 2026-09-25
updated: 2026-09-25
tags:
  - settings
  - inference
  - openrouter
---

# TASK-023: ai inference profiles

## Description

Restructure `settings.json` around a two-layer **inference catalog**: named **providers** (how to call a backend — credentials, base URL) and named **profiles** (provider + model_name). Each consumer (language, agent, summarizer, vision, embeddings, live eval) selects a profile by id via a `model` field. Default text stack moves to OpenRouter `qwen/qwen3.8-27b:free` after Mistral free-tier quality degradation, while keeping a Mistral profile for experiments without code changes. Remove scattered / dead credential fields (`language.api_key`, top-level `llm.api_key`, `perception.openrouter`, duplicated OpenRouter keys under vision/embeddings).

## Target settings shape (example)

```json
{
  "inference": {
    "providers": {
      "mistral": {
        "backend": "mistral",
        "api_key": "<mistral>"
      },
      "openrouter": {
        "backend": "openrouter",
        "api_key": "<openrouter>",
        "base_url": "https://openrouter.ai/api/v1"
      }
    },
    "profiles": {
      "text_qwen27_free": {
        "provider": "openrouter",
        "model_name": "qwen/qwen3.8-27b:free"
      },
      "text_ministral14": {
        "provider": "mistral",
        "model_name": "ministral-14b-latest"
      },
      "vision_qwen_vl": {
        "provider": "openrouter",
        "model_name": "qwen/qwen3-vl-235b-a22b-thinking"
      },
      "embed_openai_small": {
        "provider": "openrouter",
        "model_name": "openai/text-embedding-3-small"
      }
    }
  },
  "mind": {
    "perception": {
      "language": { "model": "text_qwen27_free" },
      "vision": { "model": "vision_qwen_vl" },
      "audio": { "default_language": "ru-RU" }
    },
    "memory": {
      "summarizer": { "model": "text_qwen27_free" },
      "summary_store": {
        "embeddings": { "model": "embed_openai_small" }
      }
    }
  },
  "agent": {
    "model": "text_qwen27_free"
  }
}
```

Experiment example (chat on Qwen, agent on Mistral): set `language.model` / `summarizer.model` to `text_qwen27_free` and `agent.model` to `text_ministral14`.

## Scope boundary

**In scope:**

- Introduce `inference.providers` + `inference.profiles` as the single catalog for model access configuration
- Wire consumers to resolve `model` → profile → provider: language (chat + cognition), agent, summarizer, vision, embeddings, live routing eval runner
- Default production text profiles to OpenRouter `qwen/qwen3.8-27b:free`; keep a Mistral text profile for rollback/experiments
- Fail-fast at startup on missing / invalid profile or provider references
- OpenRouter chat path must support the same structured-output needs as today's Mistral path (cognition / agent / summarizer)
- Update live-eval runbook / settings contract away from `llm.api_key` + `agent.model_name`
- Remove obsolete credential fields listed in Description

**Out of scope:**

- New backends (e.g. Jev) — catalog must leave room, but no new client
- Moving secrets to environment variables or a secret store
- Changing vision / embedding *model identities* beyond relocating current values into profiles
- CLI flag to globally switch provider
- Rate-limit / retry policy redesign (belongs to other tasks such as TASK-022)

## Related documents

- [[backlog/TASK-023-ai-inference-profiles/requirements|requirements]] — requirements and acceptance criteria
- [[backlog/TASK-023-ai-inference-profiles/design|design]] — architectural solution
- [[backlog/TASK-023-ai-inference-profiles/plan|plan]] — implementation plan
- [[backlog/TASK-023-ai-inference-profiles/review|review]] — plan-compliance gate (verdict + findings)
- [[runbooks/live-routing-eval]] — live eval credentials (must be updated)

## Dependencies

- Depends on: —
- Blocks: [[TASK-022-live-agent-eval-improvements/task|TASK-022]] (live eval still reads `llm.api_key` / `agent.model_name` today)

## Notes

Section name is `inference` (not `llm`) so text, VL, embeddings, and future non-chat models share one catalog. Providers hold `backend` + credentials once; profiles only reference a provider id + `model_name`.
