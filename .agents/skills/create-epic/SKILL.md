---
name: create-epic
description: Decomposes a large body of work into a connected set of backlog tasks and fills the epic.md decomposition map + epic-level master design outline. Use when the user asks to plan, decompose, or break down an epic (EPIC-NNN); provides an epic folder, epic id, or "decompose epic N". Runs BEFORE the per-task flow; each resulting task then goes through requirements → design → plan → implementation → close. It is designed to give the agent harness a connected, context-scoped task set.
---

# Create Epic

Turn one large, connected effort into a set of backlog tasks that can each run through
`requirements → design → plan → implement → close`. This skill is the pipeline head for multi-task work.

An epic is a first-class entity, analogous to a task but at a higher level:

```
doc/backlog/
  EPIC-NNN-name/
    epic.md      ← definition, goals, decomposition map, shared branch, live rollup
    design.md    ← master design (cross-cutting architecture; source of truth for member tasks)
  TASK-NNN-slug/ ← flat task folders, each carrying `epic: EPIC-NNN` frontmatter
```

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `epic.md` | Epic folder = parent directory |
| Path to epic folder (e.g. `doc/backlog/EPIC-001-chat-context-management/`) | `epic.md` + `design.md` inside |
| Epic id (`EPIC-001`, `001`, `1`) | Find folder: `doc/backlog/EPIC-{NNN}-*/` (zero-pad to 3 digits) |
| «decompose EPIC N» / «decompose EPIC-NNN» | Same as epic id |

If multiple folders match or none exist, stop and ask.

```bash
ls -d doc/backlog/EPIC-{NNN}-*   # substitute the zero-padded id, e.g. EPIC-001
```

## Prerequisites

Before decomposition:

1. **`epic.md`** exists (created by the developer from the `new-epic` Templater template) and its **Goal / Outcomes** is filled (not a stub).
2. **`design.md`** (master design) exists at least in draft — the decomposition is cut to follow its architecture.

If either is missing or a stub, **stop** and ask the developer to create the epic from the template and sketch the goal + master design first. Do not create the epic folder yourself.

## Documentation map

Read [doc/AGENTS.md](../../../doc/AGENTS.md) first for vault structure and the **epic** conventions, and the root [AGENTS.md](../../../AGENTS.md) for IODA, coding guidelines, and the test command.

| File | Role |
|------|------|
| `EPIC-NNN/epic.md` | **Output** — fill Goal/Outcomes alignment + the whole **Decomposition** section |
| `EPIC-NNN/design.md` | **Input/Output** — master design; ensure it is coherent enough to cut tasks against; extend its outline if needed |
| `doc/design/`, `doc/design/decisions/` | Existing system architecture and ADRs the epic must respect |

## Workflow

Copy and track:

```
- [ ] Epic folder resolved
- [ ] epic.md Goal/Outcomes read; master design read
- [ ] Project docs/code reviewed for feasibility and seams
- [ ] Decomposition principle + delivery profile chosen (jointly)
- [ ] Task set drafted (id, title, size, deliverable, deps, context slice)
- [ ] Dependency graph + milestone + parallelisation defined
- [ ] epic.md Decomposition filled
- [ ] Frontmatter updated (updated date)
- [ ] Per-task creation handoff produced
```

### 1. Understand the whole

Read `epic.md` Goal/Outcomes and the master `design.md`. Skim the relevant `yoda/` modules and `tests/` to find natural seams (IODA layers, existing chokepoints, persistence boundaries).

### 2. Choose a decomposition principle and delivery profile

Decomposition and integration boundary are **chosen together** — they are coupled, not independent:

- **functional** (by IODA/dependency layer) almost always implies `integration_boundary: epic`: a single layer (e.g. "just the schema") ships no standalone value, so nothing reaches prod until the epic merges → `internal_compat: none`.
- **vertical-slice** (end-to-end features) enables an earlier boundary (`task` / `checkpoint`) for early e2e testing, but then each slice must stay backward-compatible with deployed state → `internal_compat: additive` (or `full`).

Record the result in the epic's **`## Delivery profile`** block (`integration_strategy`, `integration_boundary`, `decomposition_principle`, and the two compatibility horizons `internal_compat` + `external_contract`). Keep the two horizons separate: `internal_compat` governs states *between member tasks*; `external_contract` governs the epic's obligation to already-deployed/persisted state at merge and is always in force regardless of `internal_compat`. Downstream `create-requirements` / `create-design` / `create-plan` read this block to avoid over- or under-engineering compatibility.

**Branch mapping.** Branch assignment is integration logic and belongs here. Decide each member task's branch from `integration_strategy` and record the mapping in `epic.md` as a single source of truth:

- `epic-branch` — one shared branch for all members. Record it in the `## Delivery profile` block (and `branch:` frontmatter). No per-task column.
- `trunk-based` — members land on trunk via short-lived per-task branches (or directly behind flags). State the branch pattern (e.g. `feat/TASK-NNN-slug`, merged independently) in the `## Delivery profile` block. No per-task column.
- `sequential-branches` / release-per-checkpoint — members map to different branches by checkpoint. Add a **`Branch`** (or `Checkpoint`) column to the decomposition table giving each task its branch, and add a reference line in the `## Delivery profile` block pointing to that column.

`create-plan` leaves epic-member `branch:` empty; `implement-task` resolves the actual branch from here per the strategy above.

For most layered epics, prefer cutting by **dependency layer**, not by user-facing feature:

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

### 4. Define ordering and value

- **Dependency graph** — a `mermaid graph TD` over the task ids.
- **Milestone** — the earliest task after which the epic delivers standalone user value (lets you stop or re-prioritise safely).
- **Parallelisation** — which tasks are independent once their deps are done. (Under `epic-branch` all run on one branch, so parallel tasks are still committed sequentially; the graph just guides safe ordering. Under multi-branch strategies, parallel tasks may live on separate branches per the branch mapping.)

### 5. Fill epic.md

Fill the **`## Delivery profile`** block (from step 2) and the **Decomposition** section of `epic.md`: principle, the task table, the dependency mermaid, milestone, and parallelisation notes. Leave the **Member tasks (live rollup)** dataview block as-is — it auto-populates once tasks carry `epic: EPIC-NNN`. Set `updated` in frontmatter.

Record the **branch mapping** (step 2): for `epic-branch` / `trunk-based` in the `## Delivery profile` block (confirm `branch: feat/EPIC-NNN-slug` in frontmatter for `epic-branch`); for `sequential-branches` / release-per-checkpoint add the `Branch`/`Checkpoint` column to the decomposition table with a reference from `## Delivery profile`.

### 6. Hand off task creation

Produce a handoff list so the developer can instantiate each task with the `new-task` Templater template, passing the **epic folder** at the prompt so `epic:` frontmatter, the `## Epic` link, and the shared-branch pre-flight are wired automatically.

For each task list: `TASK-NNN | title | size | depends-on | master-design anchors | in/out scope one-liners` — these seed the task's `task.md` Description, `## Master design`, `## Scope boundary`, and `## Dependencies` sections (the template stubs them for epic members).

## Do not

- Create the epic folder or task folders yourself (developer instantiates from templates)
- Put the decomposition map in `main.md` — it belongs in `epic.md`
- Nest task folders under the epic folder — tasks stay flat with an `epic:` attribute
- Produce tasks that cannot end in a green suite on their own
- Give a task a context slice wider than it needs
- Assign per-task branches — the epic owns one shared branch

## Output

When done, briefly report:

1. Epic id and path to `epic.md`
2. Task count + one-line each (id, title, size)
3. Dependency highlights (roots, the milestone task, parallelisable sets)
4. Shared branch name
5. Handoff: the ordered task list; next step is **create-requirements** on the first unblocked task.
