---
name: create-requirements
description: Drafts and fills doc/backlog task requirements.md from task.md, project docs, and code when needed. Use when the user asks to create or complete requirements, acceptance criteria, or FR sections for a backlog task; provides a requirements template path, task folder, or task id (TASK-NN).
---

# Create Requirements

Produce a complete `requirements.md` for a backlog task from `task.md`, project documentation, and targeted code review.

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `requirements.md` | Task folder = parent directory |
| Path to task folder (e.g. `doc/backlog/TASK-03-improve-skill-selection/`) | `requirements.md` and `task.md` inside that folder |
| Task id (`TASK-03`, `03`, `3`) | Find folder: `doc/backlog/TASK-{NN}-*/` (zero-pad to 2 digits) |

If multiple folders match or none exist, stop and ask the user to clarify.

```bash
# Example: resolve by id
ls -d doc/backlog/TASK-03-*
```

## Documentation map

Read [doc/AGENTS.md](../../../doc/AGENTS.md) first for vault structure and conventions.

Per task folder (`doc/backlog/TASK-NN-name/`):

| File | Role |
|------|------|
| `task.md` | **Source of truth** for scope, description, dependencies, links |
| `requirements.md` | Output — fill or refine this file |
| `design.md` | Do not edit unless explicitly asked |
| `plan.md` | Do not edit unless explicitly asked  |

Broader context (read selectively):

- `AGENTS.md` — architectural patterns and project structure
- `doc/backlog/main.md` — project status and informal backlog notes
- `doc/architecture/` — system-level docs
- `doc/architecture/decisions/ADR-*.md` — linked or relevant ADRs
- Related tasks via `[[TASK-XX]]` links in `task.md`

## Workflow

Copy and track:

```
- [ ] Task folder resolved
- [ ] task.md read
- [ ] Project docs reviewed (AGENTS.md, doc/design/*, related tasks)
- [ ] Code reviewed (if needed for feasibility or current behavior)
- [ ] Clarifying questions asked / assumptions confirmed
- [ ] requirements.md filled and frontmatter updated with date
- [ ] Task size evaluated and task.md frontmatter updated with size
```

### 1. Read originating task

Always start with `task.md`:

- Frontmatter: `id`, `title`, `status`, `priority`, `size`, `tags`
- **Description** — what and why
- **Dependencies** — upstream/downstream tasks
- **Notes** — decisions and constraints stated informally

Do not copy the description verbatim into requirements; expand it into structured context and FRs.

### 2. Analyze project documentation

Follow [doc/AGENTS.md](../../../doc/AGENTS.md): read only what answers open questions.

Prioritize:

- `design.md` in the same task if it's already filled (align requirements; flag conflicts)
- Design docs when the task changes architecture or APIs
- Related `requirements.md` from dependency tasks for consistency

### 3. Analyze code (when necessary)

Inspect the codebase when:

- `task.md` references existing flows, entities, APIs, or domain concepts
- Acceptance criteria must reflect current behavior or extension points
- Scope boundaries depend on what is already implemented

Stay focused: grep and read files tied to the task domain (entities, flows, prompts), not broad exploration.

### 4. Ask clarifying questions

Before writing final requirements, surface gaps. Use **AskQuestion** when available; otherwise ask in chat.

Typical topics:

- In-scope vs out-of-scope boundaries
- Data model or API changes vs UI-only
- Migration / backward compatibility
- Non-functional needs (performance, logging, security, privacy, budget)
- Dependencies on other tasks or future plans

**Stop and ask** when:

- `task.md` is a stub or contradictory
- Multiple valid interpretations would change requirements materially
- Code and `task.md` disagree

You may proceed with **labeled assumptions** only after asking once; list assumptions in **Limitations and assumptions**.

### 5. Fill requirements.md

Fill the structure of the target requirements.md. 

### 6. Evaluate task size

Final task size cannot exceed `XL`. If evaluated size appears larger, then flag this fact and ask user to decompose the task.

#### Section rules

**Context** — problem, stakeholders, when it applies. Link to goals from `task.md` / `main.md` where relevant.

**Functional requirements** — one `### FR-N: …` per capability:

- Imperative description of what the application must do
- **Acceptance criteria** as `- [ ]` checkboxes; each criterion must be **testable** and unambiguous
- Number FRs sequentially; split large topics instead of one vague FR

**Non-functional requirements** — one `### NFR-N: …` per capability:

- Imperative description of what the application must do to comply with the non-functional invariants
- **Acceptance criteria** as `- [ ]` checkboxes; each criterion must be **testable** and unambiguous
- Number NFRs sequentially; split large topics instead of one vague NFR

**Limitations and assumptions** — technical limits, explicit assumptions, compatibility notes.

**Out of scope** — bullet list of what this task explicitly does **not** include (defers to other tasks).

#### Frontmatter

```yaml
---
id: TASK-NN
doc: requirements
updated: YYYY-MM-DD
---
```

Set `updated` to today when saving.

Keep the Obsidian link: `← [[task|Back to the task]]`

## Do not

- Change backlog folder structure or create tasks without explicit instruction
- Edit `design.md` or `plan.md` unless the user asks
- Duplicate long prose from `task.md` into requirements
- Invent acceptance criteria that cannot be verified
- Leave placeholder text (`Criteria 1`, `Requirement name`) in the final file

## Output

When done, briefly report:

1. Task id and path to `requirements.md`
2. Summary of FRs added (count and titles)
3. Open questions deferred to design or a follow-up task
4. Assumptions made (if any)
5. Task size (if updated)
