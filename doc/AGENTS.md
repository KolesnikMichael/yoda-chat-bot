# AGENTS.md

Instructions for AI agents working with this repository.
This folder (`doc/`) is the root of the documentation and the Obsidian vault.

## Structure

```
doc/                      ← vault root, read from here
├── AGENTS.md             ← this file, read first
├── backlog/              ← project tasks
│  ├── main.md            ← operational notes and project backlog
│  └── TASK-NNN-name/     ← single task folder
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

## How to read a task

Always start with `task.md` — it provides context and links to other files.
Then read only what you need:

| Question                                 | File              |
| ---------------------------------------- | ----------------- |
| What needs to be done?                   | `requirements.md` |
| How does it work?                        | `design.md`       |
| What exactly is to be done?              | `plan.md`         |
| How is the system structured as a whole? | `design/`         |
| How to perform the operation?            | `runbooks/`       |
|                                          |                   |

## Task Frontmatter (task.md)

```yaml
id: TASK-NNN # unique identifier
title: improve skill selection # task title
status: todo # todo | in-progress | in-review | blocked | done
priority: medium # low | medium | high | critical
size: M # XS | S | M | L | XL
tags:
  - agent
  - prompt
```

## How to find tasks

```bash
# All tasks in progress
grep -rl "status: in-progress" doc/backlog/*/task.md

# All tasks with high priority
grep -rl "priority: high" doc/backlog/*/task.md

# Task by ID
grep -rl "id: TASK-042" doc/backlog/*/task.md
```

## Agreements

- Design decisions are recorded in `design.md`, not in code comments
- Acceptance criteria are in `requirements.md` (sections FR-N)
- When a task is completed: `status` → `done`

## What an agent should NOT do

- Do not change the backlog folder structure without explicit instructions
- Do not update `plan.md` as a log - only structured steps
- Do not duplicate information between files of the same task