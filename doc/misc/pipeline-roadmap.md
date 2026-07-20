---
id: pipeline-roadmap
title: "Task pipeline — development roadmap"
updated: 2026-06-08
tags: [meta, harness, pipeline]
---

# Task pipeline — development roadmap

Backlog of improvements to the document/skill harness that drives backlog tasks
through `task → requirements → design → plan → implement → review → close`. This file tracks
**deferred** harness work; it is not a backlog `TASK` itself.

## Deferred items
### 1. e2e bot-test harness (its own backlog TASK)

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

### 2. `doc/AGENTS.md` reconciliation + canonical structure

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
