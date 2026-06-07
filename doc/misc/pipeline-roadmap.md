---
id: pipeline-roadmap
title: "Task pipeline — development roadmap"
updated: 2026-06-08
tags: [meta, harness, pipeline]
---

# Task pipeline — development roadmap

Backlog of improvements to the document/skill harness that drives backlog tasks
through `task → requirements → design → plan → implement`. This file tracks
**deferred** harness work; it is not a backlog `TASK` itself.

## Done (2026-06-08)

Adapted the ported harness (originally built for a Java/Spring + React stack) to Yoda:

- Templates (`new-task`, `new-adr`, `runbook`) translated to English; ADR path
  fixed to `doc/design/decisions/`; task ids standardized on 3-digit `TASK-NNN`.
- All section anchors renamed to English in lockstep across the 4 skills +
  `requirements-review.md`.
- Stack ported: `./mvnw`/`npm`/Liquibase/frontend/`run-*` skills/GSD removed;
  everything runs through `.venv/bin/python -m pytest`.
- IODA awareness added (new "IODA compliance" review dimension; IODA category in
  design impact + plan `Files & artifacts`; IODA + coding-guideline checklist in
  `implement-task`).
- Tests close-out made mandatory; per-step TDD (red→green) set as the default
  rhythm; final plan stage reframed to "Test sweep & coverage".

## Deferred items

### 1. `task-postmortem` skill (5th pipeline stage)

**Why.** `implement-task` now seeds `implementation-notes.md` (failures,
workarounds, `tech-debt:` markers, ADR candidates), but nothing consumes it. A
dedicated reflection pass closes the loop and keeps `design.md` / ADRs honest.

**Scope.**

- New skill `.agents/skills/task-postmortem/SKILL.md`. Pipeline becomes
  `requirements → design → plan → implement → postmortem`.
- Inputs: same task-id/folder resolution as the other skills; reads `design.md`
  (Key/Decisions made), `implementation-notes.md`, the diff of the branch.
- Behaviors:
  - **ADR detection** — scan design "Key decisions" + implementation notes for
    cross-task/architectural decisions; draft ADR(s) in `doc/design/decisions/`
    (none exist yet — this would create the first). Use the `new-adr` template.
  - **Follow-up creation** — turn `tech-debt:` markers and discovered issues into
    backlog follow-up `TASK`s (or `main.md` backlog entries) with links back.
  - **Drift reconciliation** — diff what was built vs `design.md`/`requirements.md`;
    propose doc updates where execution diverged.
  - **Docs check** — flag `AGENTS.md` / runbooks needing updates.
- Output: report of ADRs proposed, follow-ups created, drift found.

**Open questions.** Should it auto-create follow-up task folders, or only propose
them? Where do ADR candidates that are "not worth an ADR" land — `main.md`?

**Effort.** S–M (one skill file + conventions; no code).

### 2. e2e bot-test harness (its own backlog TASK)

**Meaning (confirmed).** Automated **end-to-end tests for the bot**: a Telegram
update in → reply out, with all external APIs faked.

**Why.** Current tests cover pipeline slices (`test_mind_pipelines.py`,
`test_mind_agent_pipeline.py`, `test_react_loop.py`, `tests/fakes.py`) but there is
no single "message → reply" e2e path. Agentic tasks deserve a guardrail at that
boundary.

**Scope (as a `TASK-NNN`, not a harness edit).**

- A fixture/harness that wires `Mind` (or the Telegram portal) with **all** API
  façades faked (LLM, Telegram, Redis, ChromaDB, Tavily, speech), feeds a crafted
  update through `Mind.process_message_batch`, and asserts the outbound message +
  any persisted state.
- Cover the main intents (`agent_task` / `chat` / `pass`) and at least one tool/skill
  round-trip through the ReAct loop.
- Decide isolation strategy: in-process fakes vs lightweight fake transports;
  per-test chat isolation (chats are non-persistent).

**Harness hook (after the TASK lands).** `create-plan` / `implement-task` DoD
should **require an e2e test for agentic tasks** once the harness exists.

**Effort.** M (real code + fixtures). Run requirements → design → plan on it.

### 3. `doc/AGENTS.md` reconciliation + canonical structure

**Why.** The `doc/AGENTS.md` file and its injected cursor-rule copy have drifted
(structure block, frontmatter `size` enum). The directory layout it documents
(`design/decisions/`, `runbooks/`) is partly aspirational — `doc/design/decisions/`
and `doc/runbooks/` don't exist yet.

**Scope.**

- Pick the canonical version and make file + rule identical.
- Lock `doc/design/decisions/` as the ADR home (matches the fixed `new-adr` template).
- Create `doc/design/decisions/` and `doc/runbooks/` (even if empty, with a README)
  or remove them from the documented structure until needed.
- Confirm 3-digit `TASK-NNN` everywhere (template, skills, AGENTS — done in the now-pass;
  re-verify after any future edits).

**Effort.** XS.

## Possible later

- **Skill catalog/versioning** for the harness itself (per `doc/misc/agent_systems_outlook.md`):
  treat these skills as versioned capabilities with contracts.
- **`create-task` assist** — currently `task.md` is authored by a human; a light
  skill could help structure the initial task from a one-liner.
