# AGENTS.md

Instructions for AI agents working with this repository.
This folder (`doc/`) is the root of the documentation and the Obsidian vault.

## Structure

```
doc/                      ← vault root, read from here
├── AGENTS.md             ← this file, read first
├── backlog/              ← project tasks
│  ├── main.md            ← operational notes and project backlog
│  ├── EPIC-NNN-name/     ← epic: a connected set of tasks (optional grouping)
│  │  ├── epic.md         ← goal, decomposition map, shared branch, live rollup
│  │  └── design.md       ← master design (cross-cutting; source of truth for member tasks)
│  └── TASK-NNN-name/     ← single task folder (flat; an epic member carries `epic: EPIC-NNN`)
│     ├── task.md         ← task definition, status, context, and relationships
│     ├── requirements.md ← what needs to be done and acceptance criteria
│     ├── design.md       ← how it works, solutions, diagrams
│     └── plan.md         ← step-by-step implementation plan
├── design/               ← project-level architectural documents
│  └── decisions/         ← architecture decision records
├── runbooks/             ← operational procedures
├── templates/            ← Templater templates (ignore as content)
├── .obsidian/            ← vault files (ignore as content)
└── misc/                 ← other documents (ignore as content)
```

Tasks are **flat** under `backlog/` even when they belong to an epic; membership is
the `epic:` attribute, not folder nesting. The epic owns one shared git branch; member
tasks are implemented on it rather than on per-task branches.

## How to read a task

Always start with `task.md` — it provides context and links to other files.
If it has `epic: EPIC-NNN`, read that epic's `epic.md` + the master-design sections it
points to **first**, then stay within the slice the epic assigns. Then read only what you need:

| Question                                 | File              |
| ---------------------------------------- | ----------------- |
| What needs to be done?                   | `requirements.md` |
| How does it work?                        | `design.md`       |
| What exactly is to be done?              | `plan.md`         |
| How does this task fit the bigger effort?| `EPIC-NNN/epic.md`|
| Cross-cutting architecture of the epic?  | `EPIC-NNN/design.md` |
| How is the system structured as a whole? | `design/`         |
| How to perform the operation?            | `runbooks/`       |
|                                          |                   |

## Task Frontmatter (task.md)

```yaml
id: TASK-NNN # unique identifier
epic: EPIC-NNN # owning epic, or empty for a standalone task
title: improve skill selection # task title
status: todo # todo | in-progress | in-review | blocked | done
priority: medium # low | medium | high | critical
size: M # XS | S | M | L | XL
tags:
  - agent
  - prompt
```

## Epic Frontmatter (epic.md)

```yaml
id: EPIC-NNN # unique identifier
doc: epic
title: chat context management
status: todo # todo | in-progress | in-review | blocked | done
priority: medium
branch: feat/EPIC-NNN-slug # shared branch for all member tasks
tags: []
```

## How to find tasks

```bash
# All tasks in progress
grep -rl "status: in-progress" doc/backlog/*/task.md

# All tasks with high priority
grep -rl "priority: high" doc/backlog/*/task.md

# Task by ID
grep -rl "id: TASK-042" doc/backlog/*/task.md

# All member tasks of an epic
grep -rl "epic: EPIC-001" doc/backlog/*/task.md
```

## Agreements

- Design decisions are recorded in `design.md`, not in code comments
- Acceptance criteria are in `requirements.md` (sections FR-N)
- When a task is completed: `status` → `done`
- Epic decomposition (task list, dependency graph) lives in `epic.md`, not in `main.md`
- An epic's cross-cutting design lives in `EPIC-NNN/design.md`; member tasks reference it instead of restating decisions
- All tasks of an epic share the epic's branch; do not open per-task branches for epic members

## What an agent should NOT do

- Do not change the backlog folder structure without explicit instructions
- Do not update `plan.md` as a log - only structured steps
- Do not duplicate information between files of the same task