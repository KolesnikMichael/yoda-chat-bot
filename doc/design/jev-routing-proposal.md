---
title: "jev routing proposal"
updated: 2026-09-29
status: proposal
tags:
  - agent
  - routing
  - selection
  - jev
---

# Jev routing proposal

**Status: proposal, not a contract.** Current behavior is still defined by
[[design/agent-two-phase-protocol|two-phase protocol]] and
[[design/agent-skill-selection|skill selection]].

Idea: use TypeSafe **Jev** (a System One decision model) to collapse the two
pre-execution LLM calls — intent classification (`CognitionProvider.classify_intent`)
and skill selection (`Agent._run_selection`) — into one fast typed decision.

## What Jev is

- Classifier, not an LLM: takes a text/JSON *state* plus typed questions
  (`Choice`, `Score`, `Noul`) and returns answers with per-option probabilities
  and calibrated `confidence`. Generates no text.
- ~0.24 s P50, $0.042 / 1M input tokens, output free, 32K context, text only.
- Served via OpenRouter **Decisions API** / `POST /v1/systemone` — not
  chat-completions compatible, so it needs its own API façade (`jev` backend
  slot left by TASK-023).
- Primary training language is English; other languages have lower accuracy.
- Refs: [System One](https://docs.typesafe.ai/concepts/system-one),
  [Skill suggestion cookbook](https://docs.typesafe.ai/cookbooks/skill_suggestion.md),
  [Function calling cookbook](https://docs.typesafe.ai/cookbooks/function_calling.md),
  [model page](https://openrouter.ai/typesafe/jev-1.13).

## Fit

- One request with several questions: intent `Choice` (`chat` / `agent_task`,
  optionally `pass`), skill `Choice` (catalog + `none`), verification `Noul`s.
- Catalog selection fields (`purpose`, `when_to_use`, `do_not_use_when`,
  `selection_examples`) map directly to `Choice` option descriptions.
- Typed by construction: no malformed output, no selection corrective retry.
- `confidence` gives a natural fallback gate to the LLM selector.
- `Agent.run_with_skill` already provides a selection-free execution entry.

## What Jev cannot replace

The LLM selector also *generates* data that execution depends on:

| Field | Replacement |
|-------|-------------|
| `distilled_task` | Executor receives raw user text + `recent_messages` and resolves follow-ups itself (work moves into the first execution turn) |
| `request_constraints` | Core extracts candidate hosts deterministically; one Jev `Noul` per host decides strict vs soft |

## Risks

- Russian accuracy — `corpus-v1` is mostly English; add ru cases first.
- Time-only follow-ups to fresh-data tasks (stay on `search_web`) need recent
  conversation in the state; hardest case for a classifier.
- Executor loses the pre-distilled brief; watch planning quality.
- Young vendor, single provider — keep LLM fallback for availability too.
- Mind would own skill choice (today Agent does) — needs an ADR before rollout.

## Rollout

1. **Shadow mode** — call Jev in parallel (`asyncio.gather`) with the current
   intent classifier; log choice + confidence at `debug`; no behavior change.
2. **Measure** on corpus extended with ru cases: intent accuracy, skill
   accuracy, calibration (does low confidence track errors).
3. **Merge with fallback** — high confidence → `run_with_skill` with raw text +
   recent conversation; low confidence → current `Agent.run`.
4. **Constraints** — host extraction in Core + strict/soft `Noul`.

IODA sketch: Decisions API façade (API), routing-decision Provider, Core that
builds questions from `SkillSummary` and applies the confidence gate; `jev`
backend in the inference catalog.
