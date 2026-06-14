---
name: create-requirements
description: Drafts and fills doc/backlog task requirements.md from task.md, project docs, and code when needed. Use when the user asks to create or complete requirements, acceptance criteria, or FR sections for a backlog task; provides a requirements template path, task folder, or task id (TASK-NNN). Part of the flow task → requirements → design → plan → implementation → close. It is designed to provide the agent with everything necessary to design the changes. 
---

# Create Requirements

Produce a complete `requirements.md` for a backlog task from `task.md`, project documentation, and targeted code review. This skill starts the agent pipeline: **create `requirements.md`** → create `design.md` → create `plan.md` → implement plan → close task.

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `requirements.md` | Task folder = parent directory |
| Path to task folder (e.g. `doc/backlog/TASK-007-skill-selection/`) | `requirements.md` and `task.md` inside that folder |
| Task id (`TASK-007`, `007`, `7`) | Find folder: `doc/backlog/TASK-{NNN}-*/` (zero-pad to 3 digits) |

If multiple folders match or none exist, stop and ask the user to clarify.

```bash
ls -d doc/backlog/TASK-{NNN}-*   # substitute the zero-padded id, e.g. TASK-007
```
## Prerequisites

Before requirements work:

1. **`task.md`** exists and is readable.

If `task.md` is missing or still a stub, **stop** and ask the user to fill the task template.

## Documentation map

Read [doc/AGENTS.md](../../../doc/AGENTS.md) first for vault structure and conventions, and the root [AGENTS.md](../../../AGENTS.md) for the IODA architecture and coding guidelines.

Per task folder (`doc/backlog/TASK-NNN-name/`):

| File | Role |
|------|------|
| `task.md` | **Input** — scope, dependencies, informal constraints. Do not edit unless explicitly asked |
| `requirements.md` | **Output** — fill or refine **this** file |
| `design.md` | Do not edit unless explicitly asked |
| `plan.md` | Do not edit unless explicitly asked |

Broader context (read selectively):

- If `task.md` frontmatter has `epic: EPIC-NNN`, read `doc/backlog/EPIC-NNN-*/epic.md` (decomposition, this task's deliverable + scope) and the master-design sections listed in `task.md` `## Master design` (the master design is the file `epic.md` links as `Master design`). Stay within the slice the epic assigns this task (`## Scope boundary`); do not absorb sibling tasks' scope.
- **Delivery profile (epic members).** Read the epic's `## Delivery profile` before writing FRs. Apply two compatibility horizons:
  - **internal_compat** — state reachable *between* member tasks. If `none`, do NOT add FRs/acceptance criteria that defend against intermediate cross-task deploy states (they cannot occur on the shared branch).
  - **external_contract** — the epic's obligation to already-deployed/persisted state at merge. This is ALWAYS in force regardless of `internal_compat`: keep migration/upgrade criteria that meet real Redis/ChromaDB data on first boot after the epic merges.
  - Never collapse the two: dropping internal defensiveness must not drop external upgrade safety.
- `doc/backlog/main.md` — project status and informal backlog notes
- `doc/design/` — system-level design docs
- `doc/design/decisions/ADR-*.md` — linked or relevant ADRs
- Related tasks via `[[TASK-NNN]]` links in `task.md`

## Workflow

Copy and track:

```
- [ ] Task folder resolved
- [ ] task.md read
- [ ] Project docs reviewed (design docs, ADRs, related tasks)
- [ ] Code reviewed (if needed for feasibility or current behavior)
- [ ] Clarifying questions asked / assumptions confirmed
- [ ] requirements.md filled
- [ ] Frontmatter updated (id, updated date)
```

### 1. Read originating task

Always start with `task.md`:

- Frontmatter: `id`, `epic`, `status`, `priority`, `tags`
- **Description** — what and why
- **Master design** / **Scope boundary** (epic members) — anchors to implement and the in/out scope cut
- **Dependencies** — upstream/downstream tasks
- **Notes** — decisions and constraints stated informally

Do not copy the description verbatim into requirements; expand it into structured context and FRs.

### 2. Analyze project documentation

Follow [doc/AGENTS.md](../../../doc/AGENTS.md): read only what answers open questions.

Prioritize:

- ADRs and `doc/design/` docs when the task changes design, contracts, or behavior
- `design.md` in the same task if it's already filled (align requirements; flag conflicts)
- Related `requirements.md` from dependency tasks for consistency

### 3. Analyze code (when necessary)

Inspect the codebase when:

- `task.md` references existing modules, tools, skills, or domain concepts (`Mind`, `MemoryProvider`, agent skills, …)
- Acceptance criteria must reflect current behavior or extension points
- Scope boundaries depend on what is already implemented

Stay focused: grep and read files tied to the task domain (the relevant `yoda/` modules and `tests/`), not broad exploration.

### 4. Ask clarifying questions

Before writing final FRs, surface gaps. Use **AskQuestion** when available; otherwise ask in chat.

Typical topics:

- Actors and surfaces (Telegram private vs group chat, scheduled jobs, admin, …)
- In-scope vs out-of-scope boundaries
- Data/contract changes vs prompt/behavior-only changes
- Backward compatibility (persisted state in Redis/ChromaDB, message history)
- Non-functional needs (latency, cost/budget, rate limits, hardware constraints, logging)
- Dependencies on other tasks or external APIs (LLM, Telegram, Tavily, speech)

**Stop and ask** when:

- `task.md` is a stub or contradictory
- Multiple valid interpretations would change FRs materially
- Code and `task.md` disagree

You may proceed with **labeled assumptions** only after asking once; list assumptions in **Constraints & assumptions**.

### 5. Fill requirements.md

Fill the pre-created `requirements.md`. If it doesn't exist in the resolved folder, ask the user to provide the template; do not create it yourself.

#### Section rules

**Context** — problem, stakeholders, when it applies. Link to goals from `task.md` / `main.md` where relevant.

**Functional requirements** — one `### FR-N: …` per capability:

- Imperative description of what the system must do
- **Acceptance criteria** as `- [ ]` checkboxes; each criterion must be **testable** and unambiguous
- Number FRs sequentially; split large topics instead of one vague FR

**Constraints & assumptions** — technical limits, explicit assumptions, compatibility notes.

**Out of scope** — bullet list of what this task explicitly does **not** include (defers to other tasks).

#### Frontmatter

```yaml
---
id: TASK-NNN
doc: requirements
updated: YYYY-MM-DD
---
```

Set `id` from `task.md`. Set `updated` to today when saving.

Keep the back-link line generated by the template (`← [[backlog/TASK-NNN-…/task|Back to task]]`).

## Do not

- Change backlog folder structure or create tasks without explicit instruction
- Edit `design.md` or `plan.md` unless the user asks
- Duplicate long prose from `task.md` into requirements
- Invent acceptance criteria that cannot be verified
- Invent criteria for intermediate states excluded by the epic's `internal_compat`; but never drop `external_contract` upgrade safety
- Leave placeholder text (`Criterion 1`, `Requirement name`) in the final file

## Output

When done, briefly report:

1. Task id and path to `requirements.md`
2. Summary of FRs added (count and titles)
3. Open questions deferred to design or a follow-up task
4. Assumptions made (if any)
5. Next step: when requirements are reviewed and stable, invoke **create-design** to build the architecture contract.
