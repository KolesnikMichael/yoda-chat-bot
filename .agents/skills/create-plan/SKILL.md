---
name: create-plan
description: Drafts and fills doc/backlog task plan.md from task.md, requirements.md, and design.md as the final step before implementation. Use when the user asks to create or complete a plan, implementation steps, DoD, or pre-flight checklist for a backlog task; provides a plan template path, task folder, or task id (TASK-NNN). Part of the flow task → requirements → design → plan → implementation. It is designed to give an agent harness everything it needs to execute and resume.
---

# Create Plan

Produce a complete `plan.md` for a backlog task after `task.md`, `requirements.md`, and `design.md` are filled. This skill continues the agent pipeline: create `requirements.md` → create `design.md` → **create `plan.md`** → implement plan.

The plan is the **implementation contract for an agent harness**, not a roadmap. It must give a future agent enough to:

1. Understand the task without re-reading the whole vault.
2. See the full picture of changes before starting.
3. Execute steps in a logical, resumable order with verifiable outcomes.
4. Resume from the exact step it stopped at, after a context reset or interruption.

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `plan.md` | Task folder = parent directory |
| Path to task folder (e.g. `doc/backlog/TASK-007-skill-selection/`) | `plan.md`, `design.md`, `requirements.md`, `task.md` inside that folder |
| Task id (`TASK-007`, `007`, `7`) | Find folder: `doc/backlog/TASK-{NNN}-*/` (zero-pad to 3 digits) |

If multiple folders match or none exist, stop and ask the user to clarify.

```bash
# Example: resolve by id
ls -d doc/backlog/TASK-007-*
```

## Prerequisites

Before plan work:

1. **`task.md`** exists and is readable.
2. **`requirements.md`** exists with FRs and acceptance criteria (not placeholders).
3. **`design.md`** is **substantially filled**:
   - Architecture and interfaces present
   - Key decisions recorded
   - **Open questions** = `None.` or only minor follow-ups that do not block execution
   - Impact table («System impact») filled with concrete paths/classes and IODA categories — it is the seed for the plan's **Files & artifacts** section

If `design.md` is a stub or has unresolved blocking questions, **stop** and run or ask the user to complete design first.

## Documentation map

Read [doc/AGENTS.md](../../../doc/AGENTS.md) first for vault structure, and the root [AGENTS.md](../../../AGENTS.md) for IODA, coding guidelines, and the test command (`.venv/bin/python -m pytest` from project root).

Per task folder (`doc/backlog/TASK-NNN-name/`):

| File | Role |
|------|------|
| `task.md` | **Input** — scope, dependencies, informal constraints. Do not edit unless explicitly asked |
| `requirements.md` | **Input** — FRs and acceptance criteria. Trace every FR-N into the plan. Do not edit unless explicitly asked |
| `design.md` | **Input** — architecture, interfaces, decisions, impact table. Do not edit unless explicitly asked |
| `plan.md` | **Output** — fill or refine **this** file |

Broader context (read selectively):

- If `task.md` has `epic: EPIC-NNN`, read `EPIC-NNN-*/epic.md` for this task's position/dependencies in the decomposition. 
- `doc/design/` — system-level docs and ADRs (`doc/design/decisions/`)
- `doc/runbooks/` — operational procedures relevant to deploy/maintenance steps
- `design.md` of dependency tasks linked from `task.md` for approach consistency

## Workflow

Copy and track:

```
- [ ] Task folder resolved
- [ ] task.md, requirements.md, design.md read
- [ ] Design completeness verified (no blocking open questions)
- [ ] Files & artifacts inventory built from design impact table
- [ ] Stages and steps drafted with FR traceability
- [ ] Pre-flight, risks, rollback, DoD filled
- [ ] Clarifying questions asked / assumptions confirmed
- [ ] plan.md filled
- [ ] Frontmatter updated (updated date, branch)
```

### 1. Read task, requirements, and design

In order:

- `task.md` — scope, dependencies, status (must be `todo` or `in-progress`)
- `requirements.md` — every FR-N and its acceptance criteria become **leaves** the plan must cover
- `design.md` — architecture, interfaces, **«System impact»** table, **«Decisions made»**

Do not paste full FR or design prose into the plan; reference by id (`FR-5`, `[[design#Interfaces]]`).

### 2. Verify design is execution-ready

Quick checklist before drafting:

- Every FR-N has at least one design hook (overview, architecture, interfaces, or impact row).
- **Open questions** are closed (`None.`) or marked non-blocking.
- All contracts, DTO shapes, and tool/skill schemas in design are concrete (no `Component A`, no `Option A`).
- Persistent-state / rollout / rollback strategy is implied or stated.

If something is missing — **stop** and ask the user to update design.

### 3. Build the artifacts inventory

Translate the design's impact table into the plan's **Files & artifacts** table:

- One row per file, with `IODA` category, `Op = create | edit | delete`, and the FR ids it serves.
- Group conceptually by IODA layer (Data → Core → Provider/Portal → Integration wiring → Tests → Docs) but keep the table flat.
- This is the agent's pre-execution map: scanning it should reveal the full picture of changes.

### 4. Decompose into stages and steps

Stage rules:

- One stage = one coherent slice of work that ends in a green suite (a **Checkpoint**).
- Conventional order for Yoda: `Data/DTO → Core (pure logic) → Provider/Portal (infra/user-facing) → Integration wiring → Tests`. Reorder only with reason.
- Last stage is **always** `Test sweep & coverage` (full suite + FR-level integration + manual AC), even though behavioral steps already add tests inline (see TDD below).

Step rules — every step has:

- **Stable id** `N.M` (e.g. `1.1`, `2.3`) — used as the value of `last_step` in frontmatter for resumption.
- **Top-level checkbox** `- [ ] **N.M** Title` — the resumption anchor.
- Nested fields:
  - `Files:` concrete paths (or class names if path is ambiguous)
  - `Action:` imperative description of what to do, citing concrete symbols/decisions and the **IODA category** from `design.md`
  - `Verify:` exact command or observable check. **TDD default:** for any step that changes behavior, write the failing test first (red), then implement until green — `Verify` names that test, e.g. `.venv/bin/python -m pytest tests/test_cognition_intent.py::test_x`. Pure wiring/docs steps may use a non-test observable check.
  - `Commit:` proposed atomic commit message `feat(TASK-NNN): N.M <subject>` (`fix`, `test`, `chore`, `refactor`, `docs` for non-feature work)
- Each step is **atomic**: small enough to commit, large enough to be meaningful.
- Each step has at least one explicit dependency satisfied (previous step or pre-flight).

Stage `Checkpoint`:

- After the last step of every stage, add `**Checkpoint Stage N:**` line with the verification command that proves the stage is green (`.venv/bin/python -m pytest`, or a targeted subset + a manual smoke check).

### 5. Build the FR coverage matrix

Table `FR | Steps | Verification`:

- Every FR-N from `requirements.md` must appear with at least one step id.
- `Verification` cell names the specific test (`unit tests/test_cognition_intent.py`, `integration tests/test_mind_pipelines.py`, `manual: send message in group chat`).
- If an FR has no step, either add one or document why (e.g. requirements-only prompt copy change).

### 6. Pre-flight, risks, rollback

- **Pre-flight** — concrete environment requirements specific to this task: branch name, `.venv` active, services/keys needed (LLM, Telegram, Redis, ChromaDB), seed data, baseline `pytest` green. Avoid generic boilerplate.
- **Risks** — minimum one row or `None.`. Each risk: probability, impact, mitigation tied to a stage or step. Vague risks ("something will go wrong") are not allowed.
- **Rollback** — for every irreversible step (persistent-state write, data backfill, schema/key rename) describe how to undo (clear/restore Redis keys or ChromaDB entries). For pure code changes a single line `git revert` is enough.

### 7. Definition of Done

Extend the default DoD to match the task. Always include:

- All steps marked done
- All FR acceptance criteria pass
- Full suite green: `.venv/bin/python -m pytest`
- IODA + coding guidelines (root `AGENTS.md`) respected
- `task.md`: `status: done`, `updated: <today>`
- `design.md` / ADR updated if execution diverged from design

Add task-specific items: new ADR merged, runbook updated, sample data, admin notification wired, etc.

### 8. Fill plan.md

Fill the pre-created `plan.md`. If it doesn't exist in the resolved folder, ask the user to provide the template; do not create it yourself. Mirror the structure and quality bar of the `new-task.md` plan template (atomic steps, concrete paths, TDD `Verify`, IODA categories).

#### Frontmatter

```yaml
---
id: TASK-NNN
doc: plan
updated: YYYY-MM-DD
last_step:              # resumption anchor — set to last COMPLETED step id (e.g. 2.3); empty = not started
branch:                 # feat/TASK-NNN-...
---
```

Set `updated` to today when saving. Leave `last_step` empty. **Branch:** for a standalone task set `branch` to `feat/TASK-NNN-short-name`. For a task with `epic: EPIC-NNN`, **leave `branch` empty**.

Keep the Obsidian links: `← [[task|Back to task]] | [[requirements|Requirements]] | [[design|Design]]`

#### Section rules

**Overview** — 1 dense paragraph: what we build and why, no scope expansion. Reader grasps the task without `task.md`.

**Goal / Non-goals** — `Goal` is the observable end state; `Non-goals` is verbatim from requirements **Out of scope** (compressed if very long).

**Context to load** — explicit list of files the agent must read before step 1. Always include `requirements.md`, `design.md`, root `AGENTS.md` (IODA), `coding_behavior.md`; add ADRs and dependency-task design files when relevant.

**Pre-flight** — checklist with the actual environment for this task (branch name, `.venv` active, keys/services up, sample data, baseline `pytest` green). No generic "all set".

**Files & artifacts** — table copied from design impact, transformed: `Path | IODA | Op | FR`. This is the inventory of all changes.

**Stages** — see step rules above. Use `### Stage N:` headers and `- [ ] **N.M** Title` step bullets with nested `Files / Action / Verify / Commit`.

**Stage dependencies** — small mermaid `graph LR` if there are ≥3 stages or non-trivial parallelism. Skip for ≤2 stages.

**FR coverage (traceability)** — required table; one row per FR-N.

**Risks** — required, at least one row or `None.`.

**Rollback** — required for tasks with persistent-state or destructive changes; one-liner `git revert` is fine for pure code tasks.

**Definition of Done** — task-specific extensions on top of the defaults.

#### Traceability (required check before saving)

- Every FR-N appears in the **FR coverage** table → at least one step id.
- Every row in design's impact table appears in **Files & artifacts** (or is explicitly deferred with a note).
- Every irreversible step has a matching line in **Rollback**.
- **Definition of Done** mentions all task-specific deliverables (ADR merged, runbook updated, etc.).

## Do not

- Change backlog folder structure or create tasks without explicit instruction
- Edit `task.md`, `requirements.md`, or `design.md` unless the user asks
- Treat `plan.md` as a journal — `last_step` and checkboxes are the only mutable state during execution (`doc/AGENTS.md`)
- Duplicate long prose from requirements or design — reference by id
- Leave template placeholders (`<paths>`, `<subject>`, `Component A`, `FR-N`) in the final file
- Start plan when `design.md` has unresolved blocking open questions
- Invent steps that do not map to a file or an FR

## Output

When done, briefly report:

1. Task id and path to `plan.md`
2. Stage/step counts (e.g. "4 stages, 18 steps")
3. FR coverage summary (`N/N` FRs covered)
4. Pre-flight assumptions about environment (keys up, branch name, …)
5. Open items deferred to execution time, if any (label as assumptions, not blockers)
