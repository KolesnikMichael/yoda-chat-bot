# AGENTS.md

`doc/` is the documentation root and Obsidian vault. Code conventions (IODA, coding
guidelines, tests): [../AGENTS.md](../AGENTS.md).

## Layout

```
doc/                      ← vault root, read from here
├── AGENTS.md             ← this file
├── backlog/              ← project tasks
│  ├── main.md            ← operational notes and project backlog
│  ├── EPIC-NNN-name/     ← epic: a connected set of tasks (optional grouping)
│  │  ├── epic.md         ← goal, decomposition map, shared branch, live rollup
│  │  └── design.md       ← master design (cross-cutting; source of truth for member tasks)
│  └── TASK-NNN-name/     ← single task folder (flat; an epic member carries `epic: EPIC-NNN`)
│     ├── task.md         ← task definition, status, context, and relationships
│     ├── requirements.md ← what needs to be done and acceptance criteria
│     ├── design.md       ← how it works, solutions, diagrams
│     ├── plan.md         ← step-by-step implementation plan
│     ├── review.md       ← review findings + verdict
│     └── implementation-notes.md ← (optional) incidents, workarounds, ADR candidates from execution
├── design/               ← project-level architectural documents
│  └── decisions/         ← architecture decision records (ADRs)
├── runbooks/             ← operational procedures
├── templates/            ← Templater templates (ignore as content)
├── .obsidian/            ← vault files (ignore as content)
└── misc/                 ← other documents (ignore as content)
```

Tasks are **flat** under `backlog/` even when they belong to an epic; membership is
the `epic:` attribute in `task.md`, not folder nesting. Branch strategy for epic
members is defined in the epic's `epic.md` (`## Delivery profile`); see **create-epic**
and **implement-task** skills.

## Artifact roles

Always start with `task.md` — it links to the rest.

| Artifact | Role |
| -------- | ---- |
| `task.md` | Entry point: scope, status, dependencies, links |
| `requirements.md` | FR-N functional requirements and acceptance criteria |
| `design.md` | Architecture, interfaces, decisions for this task |
| `plan.md` | Implementation contract: stages, steps, FR traceability |
| `review.md` | Plan-compliance gate: `verdict`, findings, follow-ups |
| `implementation-notes.md` | Optional execution log: incidents, workarounds, ADR candidates |
| `EPIC-NNN/epic.md` | Epic goal, decomposition, delivery profile, live rollup |
| `EPIC-NNN/design.md` | Epic master design — cross-cutting architecture |
| `design/` | Project-level architecture |
| `design/decisions/` | ADRs |
| `runbooks/` | Operational procedures |

## Pipeline (agents)

Backlog work runs through skills in `.agents/skills/`. **Do not re-derive workflow
from this file** — suggest the user to invoke the matching skill.

| Phase | Skill |
| ----- | ----- |
| Decompose epic | `create-epic` |
| Requirements | `create-requirements` |
| Design | `create-design` |
| Plan | `create-plan` |
| Implement | `implement-task` |
| Review | `review-task` |
| Close | `close-task` |

Per-task flow: `create-requirements` → `create-design` → `create-plan` →
`implement-task` → `review-task` → `close-task`. Epic members: run `create-epic`
first, then the per-task flow for each member.

## Templates & frontmatter

Authoritative stubs and frontmatter: `templates/new-task.md`, `templates/new-epic.md`,
`templates/new-adr.md`. Create new tasks/epics from these templates — do not hand-roll
folder layouts.

## Vault invariants

- Do not change the `backlog/` folder layout without explicit instruction.
- Cross-cutting epic architecture belongs in the epic master design; member `design.md`
  files **reference** it, they do not restate decisions.
- Project ADRs live under `design/decisions/`.
