---
id: TASK-012
doc: plan
updated: 2026-06-18
last_step: 
branch: 
---

# TASK-012: memory provider cache ownership — Implementation plan

← [[task|Back to task]] | [[requirements|Requirements]] | [[design|Design]]

## Overview

Refactor `MemoryProvider` in-memory cache: register-under-lock, CRUD trio policy, optional int keys and `chat_id`-only `Mind` API. Blocked on [[design]] Decisions 1–5.

## Goal / Non-goals

- **Goal:** Provider owns cache lifecycle; no redundant save ceremony; clear cache vs stash naming; CRUD visibility per design.
- **Non-goals:** Stash policy, schema, compression, new Integration types.

## Context to load

- [[requirements]] — CRUD trio, IODA framing, alternatives A–F, FR-1…FR-3
- [[design]] — decisions
- `yoda/mind/memory/memory.py`, `yoda/mind/mind.py`
- `yoda/mind/agent/tools/delete_user_data_tool.py`
- [[ADR-000-sensitive-data-persistence]]
- Root `AGENTS.md`, `coding_behavior.md`

## Pre-flight

- [ ] Design Decisions 1–5 resolved
- [ ] Baseline tests green: `.venv/bin/python -m pytest`

## Files & artifacts

| Path | IODA | Op | FR |
|------|------|----|----|
| `yoda/mind/memory/memory.py` | Provider | edit | FR-1, FR-3 |
| `yoda/mind/mind.py` | Integration | edit | FR-1, FR-3 |
| `yoda/mind/agent/tools/delete_user_data_tool.py` | Tool | edit (if F) | FR-3 |
| `tests/fakes.py` | Test | edit | FR-1…FR-3 |
| `tests/test_memory_operation.py` | Test | edit | FR-1…FR-3 |

## Stages

### Stage 1: Provider cache internals

- [ ] **1.1** Register-under-lock + key type + private CRUD per design
  - Files: `memory.py`
  - Action: `_register` / int keys / hide get-save-forget per Decisions 1–3, 6
  - Verify: `.venv/bin/python -m pytest tests/test_memory_operation.py`
  - Commit: `refactor(TASK-012): 1.1 provider cache internals`

### Stage 2: Callers — Mind, tool, tests

- [ ] **2.1** Mind: remove get/save ceremony; optional `chat_id`-only append API (Decision 4)
  - Files: `mind.py`
  - Verify: `.venv/bin/python -m pytest tests/test_mind_pipelines.py tests/test_mind_agent_pipeline.py`
  - Commit: `refactor(TASK-012): 2.1 mind cache API`

- [ ] **2.2** DeleteUserDataTool + fakes + remaining tests (Decision 5)
  - Files: `delete_user_data_tool.py`, `tests/fakes.py`, compression/maintenance tests as needed
  - Verify: `.venv/bin/python -m pytest`
  - Commit: `refactor(TASK-012): 2.2 callers and tests`

## FR coverage

| FR | Steps | Verification |
|----|-------|--------------|
| FR-1 | 1.1, 2.1 | mind + memory tests |
| FR-2 | 1.1, 2.2 | full suite; no new stash calls |
| FR-3 | 1.1, 2.2 | design doc + tool path |

## Definition of Done

- [ ] All plan steps checked
- [ ] FR-1…FR-3 pass
- [ ] Full suite green
- [ ] `task.md`: `status: done`
