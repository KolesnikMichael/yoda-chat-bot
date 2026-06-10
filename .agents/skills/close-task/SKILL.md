---
name: close-task
description: Closes a backlog task after implement-task finishes — verifies DoD, harvests implementation-notes.md into design reconciliation, ADRs, and follow-up tasks, flips statuses, and runs the epic close-out check (milestone, all-members-done, shared-branch merge proposal). Use when the user asks to close, finalize, wrap up, or run a postmortem for a backlog task; provides a task folder or task id (TASK-NNN). Tail of the flow task → requirements → design → plan → implementation → close. It is designed to extract the most valuable information and insights from the entire flow.
---

# Close Task

Close out an implemented backlog task: verify it is genuinely done, turn what the
implementation *taught us* into durable artifacts (design updates, ADRs, follow-up
tasks), and check whether the owning epic reached its milestone or completion.
This is the tail of the pipeline: requirements → design → plan → implement → **close**.

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to task folder (e.g. `doc/backlog/TASK-007-skill-selection/`) | Read `plan.md`, `task.md`, `implementation-notes.md` inside |
| Task id (`TASK-007`, `007`, `7`) | Find folder: `doc/backlog/TASK-{NNN}-*/` (zero-pad to 3 digits) |

If multiple folders match or none exist, stop and ask.

```bash
ls -d doc/backlog/TASK-{NNN}-*   # substitute the zero-padded id, e.g. TASK-007
```

## Prerequisites

1. **`plan.md`** executed: all step checkboxes checked and the full suite green
   (`.venv/bin/python -m pytest`). If steps remain unchecked or the suite is red —
   **stop** and ask: finish via `implement-task`, or explicitly approve a **partial
   close** (remaining work then becomes follow-up proposals, recorded in the report).
2. Read the root `AGENTS.md` and [doc/AGENTS.md](../../../doc/AGENTS.md) for vault conventions.

## Documentation map

| File | Role |
|------|------|
| `plan.md` | **Input** — Definition of Done, executed steps |
| `implementation-notes.md` | **Input** — incidents, workarounds, divergences, ADR candidates (absent = clean run) |
| `design.md` (task) | **Output** — reconcile with what was actually built |
| Epic master design (linked from `epic.md` as `Master design`) | **Output (on confirmation)** — cross-cutting corrections |
| `task.md`, `epic.md` | **Output** — status/updated flips |
| `doc/design/decisions/ADR-*.md` | **Output (via handoff)** — accepted ADR candidates |

## Workflow

Copy and track:

```
- [ ] Task folder resolved; plan + implementation-notes read
- [ ] Definition of Done verified (suite green, all items)
- [ ] Task design.md reconciled with as-built reality
- [ ] Master-design corrections proposed (epic members, if any)
- [ ] ADR candidates triaged; handoff produced for accepted ones
- [ ] Follow-up tasks / notes proposed
- [ ] Statuses flipped (task.md done, updated dates)
- [ ] Epic rollup checked (milestone / all done / merge proposal)
```

### 1. Verify Definition of Done

Walk every item in `plan.md` **Definition of Done**: re-run the full suite, confirm
FR acceptance criteria are test-covered, IODA/coding-guideline review done, docs
updated. Anything unmet → stop and resolve (or record it under the user-approved
partial close).

### 2. Harvest implementation notes

Read `implementation-notes.md` (skip this step if absent) and sort every entry into
exactly one bucket:

- **Design divergence** — what was built differs from `design.md` → step 3.
- **Cross-cutting divergence** — affects the epic's master design or other tasks → step 3 (proposal).
- **ADR candidate** — a decision with architectural or cross-task reach → step 4.
- **Tech debt / deferred work** — workarounds with a revisit condition → step 5.
- **Plan-quality lesson** — what the plan got wrong; goes to the report only (feedback for future `create-plan` runs).

### 3. Reconcile design

- Update the task's `design.md` so it describes what was actually built (decisions,
  interfaces, impact table). Set `updated`.
- For cross-cutting divergences in an epic member: **propose** the master-design patch
  in chat (section, old → new) and apply it only after the user confirms. Sibling
  tasks not yet designed must inherit the corrected truth, not the stale one.

### 4. Triage ADR candidates

For each candidate, recommend **accept** (architectural/cross-task reach, will be
questioned later) or **drop** (local detail already captured in `design.md`). For
accepted ones: the developer creates the file from the `new-adr` Templater template
(next free number: `ls doc/design/decisions/`), then you fill Context / Options /
Decision / Consequences and link the originating task under **Related documents**.

### 5. Propose follow-ups

- Work that earned its own task (deferred scope, tech debt with a revisit condition):
  propose `title | size | depends-on | rationale`; the developer creates it from the
  `new-task` Templater template. For epic members, flag whether it belongs inside the
  epic (gets `epic:`) or stands alone.
- Smaller observations: offer to append one-liners to `doc/backlog/main.md` Notes
  (`## Fix` / `## Add` / `## See`) — only with user approval.

### 6. Flip statuses

- `task.md`: `status: done`, `updated: <today>` (if `implement-task` has not already).
- `plan.md`: `updated: <today>`. Leave step checkboxes and `last_step` as executed —
  the plan is a record, not a journal to rewrite.
- Epic rollups (`epic.md`, `main.md`) update themselves via dataview — do not edit tables.

### 7. Epic close-out check (members only)

If `task.md` has `epic: EPIC-NNN`:

```bash
grep -l "epic: EPIC-{NNN}" doc/backlog/*/task.md | xargs grep -H "^status:"
```

- **Milestone task done** (per `epic.md` **Milestone**) → report that the epic now
  delivers standalone user value; offer to merge the shared branch into `main` early.
- **All member tasks done** → epic close-out: resolve or explicitly carry over the
  master design's **Open questions**, harvest `epic.md` **Notes** (same buckets as
  step 2), set `epic.md` `status: done`, `updated: <today>`, and propose merging the
  shared branch into `main`.
- Otherwise → report progress (`X/N done`) and the next unblocked task per the
  dependency graph.

Never merge or delete branches yourself — propose; the user merges or explicitly asks.

## Do not

- Close while the suite is red or DoD items are open (unless the user explicitly approved a partial close)
- Create ADR or task files from templates yourself — handoff to the developer, then fill
- Rewrite `plan.md` history (checkboxes, steps, `last_step`) — corrections live in `design.md` and the notes
- Edit the master design without user confirmation
- Merge, rebase, or delete branches without an explicit request

## Output

When done, briefly report:

1. Task id; DoD status (full close / partial close with carried-over items)
2. Notes harvested: counts per bucket; plan-quality lessons verbatim
3. Design updates applied (task `design.md`; master-design patches proposed/applied)
4. ADR handoffs (accepted candidates with proposed numbers/names) and dropped candidates with reasons
5. Follow-up proposals (`title | size | depends-on`) and main.md note suggestions
6. Epic state: `X/N` member tasks done, milestone reached or not, merge proposal if applicable; next unblocked task — start it with **create-requirements**.
