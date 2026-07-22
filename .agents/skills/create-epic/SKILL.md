---
name: create-epic
description: Decomposes a large body of work into a connected set of backlog tasks and fills the epic.md decomposition map + epic-level master design outline. Use when the user asks to plan, decompose, or break down an epic (EPIC-NNN); provides an epic folder, epic id, or "decompose epic N". Runs BEFORE the per-task flow; each resulting task then goes through requirements → design → plan → implementation → review → close. It is designed to give the agent harness a connected, context-scoped task set.
---

# Create Epic

Turn one large, connected effort into a set of backlog tasks that can each run through
`requirements → design → plan → implement → review → close`. This skill is the pipeline head for multi-task work.

An epic is a first-class entity, analogous to a task but at a higher level:

```
doc/backlog/
  EPIC-NNN-name/   ← active epic only (never create under archive/)
    epic.md        ← definition, goals, decomposition map, shared branch, live rollup
    design.md      ← master design (cross-cutting architecture; source of truth for member tasks)
  archive/         ← frozen historical epics — do not resolve or edit here (see doc/AGENTS.md)
  TASK-NNN-slug/   ← flat task folders, each carrying `epic: EPIC-NNN` frontmatter
```

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `epic.md` | Epic folder = parent directory |
| Path to epic folder (e.g. `doc/backlog/EPIC-001-chat-context-management/`) | `epic.md` + `design.md` inside |
| Epic id (`EPIC-001`, `001`, `1`) | Find folder: `doc/backlog/EPIC-{NNN}-*/` only (exclude `backlog/archive/`) |
| «decompose EPIC N» / «decompose EPIC-NNN» | Same as epic id |

If multiple folders match or none exist, stop and ask. Do **not** look under
`doc/backlog/archive/` for create/decompose work — archived epics are frozen.

```bash
ls -d doc/backlog/EPIC-{NNN}-*   # active epics only; substitute zero-padded id, e.g. EPIC-001
# never: ls doc/backlog/archive/EPIC-*
```

## Prerequisites

Before decomposition:

1. **`epic.md`** exists (created by the developer from the `new-epic` Templater template) and its **Goal / Outcomes** is filled (not a stub).
2. **`design.md`** (master design) exists at least in draft — the decomposition is cut to follow its architecture.

If either is missing or a stub, **stop** and ask the developer to create the epic from the template and sketch the goal + master design first. Do not create the epic folder yourself.

## Documentation map

Read [doc/AGENTS.md](../../../doc/AGENTS.md) for vault layout; root [AGENTS.md](../../../AGENTS.md) for IODA, coding guidelines, and the test command.

| File | Role |
|------|------|
| `EPIC-NNN/epic.md` | **Output** — fill Goal/Outcomes alignment + the whole **Decomposition** section |
| `EPIC-NNN/design.md` | **Input/Output** — master design; ensure it is coherent enough to cut tasks against; extend its outline if needed |
| `doc/design/`, `doc/design/decisions/` | Existing system architecture and ADRs the epic must respect |
| `doc/templates/new-task.md` | **Reference** — layout for member-task folders the agent creates in step 6 |

## Workflow

Copy and track:

```
- [ ] Epic folder resolved
- [ ] epic.md Goal/Outcomes read; master design read
- [ ] Project docs/code reviewed for feasibility and seams
- [ ] Decomposition principle + delivery profile options drafted for user consideration
- [ ] Decomposition principle + delivery profile approved by user; epic.md Delivery profile filled
- [ ] Task set drafted (id, title, size, deliverable, deps, context slice)
- [ ] Dependency graph + milestone + parallelisation defined
- [ ] Task set presented for approval; remarks addressed
- [ ] epic.md Decomposition filled; frontmatter updated
- [ ] Member task folders + stub docs created (new-task.md layout)
- [ ] Each task.md filled from decomposition
```

### 1. Understand the whole

Read `epic.md` Goal/Outcomes and the master `design.md`. Skim the relevant `yoda/` modules and `tests/` to find natural seams (IODA layers, existing chokepoints, persistence boundaries).

### 2. Choose decomposition principle and delivery profile — approval gate

Decomposition and integration boundary are **chosen together** — they are coupled, not independent:

- **functional** (by IODA/dependency layer) almost always implies `integration_boundary: epic`: a single layer (e.g. "just the schema") ships no standalone value, so nothing reaches prod until the epic merges → `internal_compat: none`.
- **vertical-slice** (end-to-end features) enables an earlier boundary (`task` / `checkpoint`) for early e2e testing, but then each slice must stay backward-compatible with deployed state → `internal_compat: additive` (or `full`).

**Branch mapping** couples to `integration_strategy`:

- `epic-branch` — one shared branch for all members (`branch:` frontmatter + `## Delivery profile`). No per-task column.
- `trunk-based` — short-lived per-task branches (or flags on trunk). State the branch pattern in `## Delivery profile`.
- `sequential-branches` / release-per-checkpoint — a **`Branch`** (or `Checkpoint`) column in the decomposition table; reference it from `## Delivery profile`.

`create-plan` leaves epic-member `branch:` empty; `implement-task` resolves the actual branch from here per the strategy above.

**Evaluate and present (do not decompose yet).** Draft up to **three** viable combinations of `decomposition_principle` + delivery profile (`integration_strategy`, `integration_boundary`, `internal_compat`, `external_contract`, branch mapping). For each option give a **brief** summary: what it implies for task count, ordering, compatibility work, and branch workflow. End with **one recommendation** from the perspective of **implementation simplicity** (least ceremony, fewest cross-task contracts, clearest checkpoints).

**Stop and wait for explicit user approval** of one option (or a user-specified variant). Do not proceed to steps 3–6 until approved.

**After approval:** record the chosen profile in `epic.md` **`## Delivery profile`** (and `branch:` frontmatter when using `epic-branch`). Keep the two compatibility horizons separate: `internal_compat` governs states *between member tasks*; `external_contract` governs the epic's obligation to already-deployed/persisted state at merge and is always in force regardless of `internal_compat`. Downstream `create-requirements` / `create-design` / `create-plan` read this block.

For most layered epics, the recommended default is cutting by **dependency layer**, not by user-facing feature:

```
data model / schema → ingest behaviour → pure Core algorithms → Integration shell → Providers → full apply pipeline → wiring → external stores → agent skills
```

Each task should:

- be **independently implementable and testable**, ending in a green suite (its own Checkpoint);
- own **one coherent slice** (ideally one or few IODA layers);
- have an explicit **deliverable** (observable user/system value or a foundation other tasks build on);
- carry a **minimal context slice**: the exact master-design sections it needs + the sibling tasks it depends on. This is the whole point of the epic split — it keeps each task's context tight.

### 3. Draft the task set

For every task, record:

- **id** (`TASK-NNN`, globally sequential), **title**, **size** (`XS`–`XL`), **deliverable**
- **Depends on / Blocks** (by `TASK-NNN`)
- **Master-design anchors** — the specific `[[<master-design>#Section]]` headings this task implements (the task's `requirements`/`design` skills load only these)

Keep tasks balanced: split anything that would be `XL`; merge trivially-coupled `XS` slices only if they share the same layer.

Resolve the next free `TASK-NNN` ids before presenting:

```bash
grep -rh '^id: TASK-' doc/backlog/*/task.md | sort
```

### 4. Define ordering and value

- **Dependency graph** — a `mermaid graph TD` over the task ids.
- **Milestone** — the earliest task after which the epic delivers standalone user value (lets you stop or re-prioritise safely).
- **Parallelisation** — which tasks are independent once their deps are done. (Under `epic-branch` all run on one branch, so parallel tasks are still committed sequentially; the graph just guides safe ordering. Under multi-branch strategies, parallel tasks may live on separate branches per the branch mapping.)

### 5. Present task set for approval — approval gate

Present the full draft decomposition concisely: the task table (id, title, size, deliverable), dependency graph, milestone, and parallelisation notes.

**Stop and wait for explicit user approval.** If the user has remarks, revise steps 3–4 and re-present until accepted. Do not write `epic.md` Decomposition or create task folders until the task set is approved.

### 6. Finalize epic and create member tasks

After the task set is approved:

1. **Fill `epic.md`** — the **Decomposition** section (principle aligned with `decomposition_principle`, task table, dependency mermaid, milestone, parallelisation). Leave **Member tasks (live rollup)** as-is. Bump `updated` in frontmatter. For `sequential-branches` / release-per-checkpoint, include the `Branch`/`Checkpoint` column and the reference from `## Delivery profile`.

2. **Create each member task folder** under `doc/backlog/TASK-NNN-slug/` with the same file set and frontmatter stubs as [`new-task.md`](../../../doc/templates/new-task.md) would produce for an epic member:
   - `task.md` — frontmatter: `id`, `epic: EPIC-NNN`, `title`, `status: todo`, `priority`, `size`, dates, `tags`
   - `requirements.md`, `design.md`, `plan.md` — stub bodies and frontmatter from the template; epic-member `plan.md` keeps `branch:` empty and includes the shared-epic-branch pre-flight line

3. **Fill each `task.md`** from the approved decomposition:
   - **Description** — one paragraph (what and why)
   - **Master design** — anchor links from step 3
   - **Scope boundary** — in/out one-liners from the context slice
   - **Dependencies** — Depends on / Blocks by `TASK-NNN`
   - **size** in frontmatter

Leave `requirements.md`, `design.md`, and `plan.md` as template stubs — the per-task pipeline (`create-requirements` → …) fills them.

## Do not

- Create the epic folder yourself (developer instantiates from `new-epic` template)
- Proceed past step 2 or step 5 without explicit user approval
- Put the decomposition map in `main.md` — it belongs in `epic.md`
- Nest task folders under the epic folder — tasks stay flat with an `epic:` attribute
- Produce tasks that cannot end in a green suite on their own
- Give a task a context slice wider than it needs
- Use per-task `branch:` in epic-member `plan.md` — branch mapping lives in the epic's Delivery profile

## Output

When done, briefly report:

1. Epic id and path to `epic.md`
2. Approved delivery profile (one line)
3. Task count + one-line each (id, title, size)
4. Paths to created task folders
5. Dependency highlights (roots, the milestone task, parallelisable sets)
6. Shared branch name (or branch pattern, per strategy)
7. Next step: **create-requirements** on the first unblocked task.
