---
name: create-design
description: Drafts and fills doc/backlog task design.md from task.md and requirements.md after requirements review. Use when the user asks to create or complete design, architecture decisions, API/data model sections, or diagrams for a backlog task; provides a design template path, task folder, or task id (TASK-NNN). Part of the flow task → requirements → design → plan → implementation. It is designed to give an agent harness everything it needs to plan the implementation.
---

# Create Design

Produce a complete `design.md` for a backlog task from `task.md` after reviewing `requirements.md`, project architecture, and targeted code. This skill continues the agent pipeline: create `requirements.md` → **create `design.md`** → create `plan.md` → implement plan.

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `design.md` | Task folder = parent directory |
| Path to task folder (e.g. `doc/backlog/TASK-007-skill-selection/`) | `design.md`, `requirements.md`, and `task.md` inside that folder |
| Task id (`TASK-007`, `007`, `7`) | Find folder: `doc/backlog/TASK-{NNN}-*/` (zero-pad to 3 digits) |

If multiple folders match or none exist, stop and ask the user to clarify.

```bash
# Example: resolve by id
ls -d doc/backlog/TASK-007-*
```

## Prerequisites

Before design work:

1. **`task.md`** exists and is readable.
2. **`requirements.md`** exists and is **substantially filled** (context, FR-N with acceptance criteria, not placeholders).

If `requirements.md` is missing or still a stub (`Criterion 1`, empty FR list), **stop** and run or ask the user to complete requirements.

## Documentation map

Read [doc/AGENTS.md](../../../doc/AGENTS.md) first for vault structure, and the root [AGENTS.md](../../../AGENTS.md) for the **IODA architecture** (Integration / Core / Provider / Portal / Data / API), naming conventions, and hard dependency rules — the design must comply with them.

Per task folder (`doc/backlog/TASK-NNN-name/`):

| File | Role |
|------|------|
| `task.md` | **Input** — scope, dependencies, informal constraints. Do not edit unless explicitly asked |
| `requirements.md` | **Input** — FRs and acceptance criteria to satisfy. Do not edit unless explicitly asked |
| `design.md` | **Output** — fill or refine **this** file |
| `plan.md` | Do not edit unless explicitly asked |

Broader context (read selectively):

- **Epic membership:** if `task.md` has `epic: EPIC-NNN`, the epic's `design.md` (master design) is the **source of truth** for cross-cutting architecture. Read `EPIC-NNN-*/epic.md` + the master-design sections this task implements, then **reference** them (`[[<master-design>#Section]]`) instead of restating decisions. Put only this task's local design here; raise any cross-task decision to the master design (flag it in the report).
- `doc/design/` — system-level design docs
- `doc/design/decisions/ADR-*.md` — binding decisions (patterns, conventions, …)
- `design.md` and `requirements.md` of dependency tasks linked from `task.md` for contract continuity

## Workflow

Copy and track:

```
- [ ] Task folder resolved
- [ ] task.md read
- [ ] requirements.md read
- [ ] Project docs and dependency designs reviewed
- [ ] Code reviewed (if needed for feasibility or current behavior)
- [ ] Requirements review checklist completed (incl. IODA compliance)
- [ ] Clarifying questions asked / open items resolved
- [ ] design.md filled
- [ ] Task size estimated
- [ ] Frontmatters updated (updated date, size in task.md)
```

### 1. Read task and requirements

Always start with `task.md`, then `requirements.md`:

- Map every **FR-N** to a future design section (overview, data model, interfaces, impact, …).
- Note **Out of scope** and **Constraints & assumptions** — design must not expand scope.
- Follow `[[TASK-NNN]]` and ADR links in requirements.

Do not paste full FR text into design; reference by id (`[[requirements|FR-5]]` or `FR-5` in prose).

### 2. Analyze project documentation and code

Follow [doc/AGENTS.md](../../../doc/AGENTS.md): read only what answers open questions.

Prioritize:

- ADRs and `doc/design/` when the task changes contracts, persistence, or behavior
- `design.md` of dependency tasks (shared modules, agent skills, memory model)
- Existing `design.md` in the same task if partially filled (extend, do not reset without reason)

Inspect the codebase when:

- Requirements assume current components (`Mind`, `Perception`, `MemoryCore`/`MemoryProvider`, agent skills, API façades)
- Feasibility or impact table needs real module/class names
- Requirements and code disagree — **stop and ask**

Stay focused: grep and read files tied to the task domain in `yoda/` and `tests/`, not broad exploration.

### 3. Review requirements (checklist)

With all the above information collected, run the checklist in [requirements-review.md](requirements-review.md) **before** writing architecture. Record findings:

- **Gap** — stop; propose FR patch in chat; do not proceed until user confirms; do not edit `requirements.md` unless the user asks.
- **Conflict** — stop; resolve with the user; document the resolution in **Decisions made**.
- **Pass** — no action.

Summarize review in chat (short table: dimension → status → notes).


### 4. Ask clarifying questions and resolve open items

Before finalizing design, close gaps found in the review. Use **AskQuestion** when available; otherwise ask in chat.

Typical topics:

- Contract choices (new tool/skill vs extending an existing one; prompt vs code)
- Persistent-state strategy and cleanup (Redis keys, ChromaDB collections, history)
- IODA placement (which category a new class belongs to; how Integrations pass data between Operations)
- Backward compatibility with stored conversations/profiles
- Cross-task ownership (fix in this task vs follow-up TASK)

**Stop and ask** when:

- Requirements are contradictory or untestable
- Multiple architectures would satisfy FRs with different cost/risk
- A decision belongs in an ADR but none exists

Resolved items go to **Decisions made** (table) and/or **Key decisions**; unresolved items stay in **Open questions** with owner and impact on FRs.

You may proceed with **labeled assumptions** only after asking once; list them in **Decisions made** or a short note under **Solution overview**.

### 5. Fill design.md

Fill the pre-created `design.md`. If it doesn't exist in the resolved folder, ask the user to provide the template; do not create it yourself.

#### Section rules

**Solution overview** — one dense paragraph: approach + rationale. The agent should understand *what* without reading decisions yet.

**Architecture** — mermaid diagram when multiple components interact; optional component table. Name each new/changed component with its **IODA category** (Integration / Core / Provider / Portal / Data / API) and respect naming (`*Core`, `*Provider`, `*Portal`).

**Key decisions** — one `### Decision N:` per non-obvious choice:

- **Context** / **Options** / **Choice:** (mandatory pattern from template)
- Tie each decision to FR ids
- Flag any decision with cross-task or architectural reach as an **ADR candidate** (handed off to the postmortem step)

**Interfaces** — concrete method signatures, tool/skill schemas, DTO shapes, message contracts where they remove ambiguity for implementers.

**System impact** — table: file/class → IODA category → change → FR. Populated at the file / class level: this table is **the source for the «Files & artifacts»** section of `plan.md`. Empty cells or aggregates like "mind changes" will make the plan unexecutable. Verify the change respects IODA hard rules (Operations never depend on other Operations/Integrations; the Integration passes data between Operations).

**Decisions made (from requirements review)** — table for items clarified during review.

**Open questions** — only what truly blocks `plan.md`; each item notes affected FRs. Empty section: `None.` when everything is closed.

#### Task size

Use the following guidelines as a baseline for estimating the task size, adjusting for the expected complexity of the affected business logic:

- `XS` — 1-2 files, no persistent-state change, up to 2 FR
- `S` — up to ~10 files, 3-5 FR
- `M` — multiple IODA layers (Data + Core + Provider/Portal + Integration wiring), 6-10 FR
- `L` — 10-15 FR, or a non-trivial persistent-state/migration concern, or more than one subsystem
- `XL` — >15 FR, or clearly decomposed into `S`-`L` parts with their own requirements/design/plan/implement cycle

#### Frontmatters

```yaml
---
id: TASK-NNN
doc: design
updated: YYYY-MM-DD
---
```

Set `updated` to today when saving. Set `size` in `task.md` to the estimated value.

Keep the Obsidian links: `← [[task|Back to task]] | [[requirements|Requirements]]`

#### Traceability

Every FR-N should be traceable to at least one of: overview, architecture, a key decision, interfaces, or impact table. If an FR has no design hook, either add it or flag as requirements-only (e.g. pure prompt copy change) in the review summary.

## Do not

- Change backlog folder structure or create tasks without explicit instruction
- Edit `requirements.md` unless the user asks (report gaps and proposed FR wording in chat instead)
- Duplicate long FR prose into design
- Leave template placeholders (`Option A`, `Component A`, `Name`) in the final file
- Start design when `requirements.md` is still a stub
- Leave **System impact** empty or filled with aggregates like «mind changes» — `create-plan` cannot derive an artifact inventory from such rows
- Place a class in violation of IODA (Operation depending on another Operation/Integration, wrong `*Core`/`*Provider`/`*Portal` naming)
- Close design with **Open questions** that block plan execution; mark any remaining items as non-blocking with a one-line impact note

## Output

When done, briefly report:

1. Task id and path to `design.md`
2. Requirements review summary (checklist dimensions → pass/gap, incl. IODA compliance)
3. Key decisions recorded (count and one-line each); flag ADR candidates
4. Open questions deferred to plan or follow-up (if any)
5. Assumptions made (if any)
6. Suggested updates to `requirements.md` (if review found gaps), without applying unless asked
7. Plan readiness: **Open questions** = `None.` (or non-blocking) **and** «System impact» lists concrete files/classes with IODA categories → ready to invoke **create-plan**. Otherwise list what still needs to be closed.
8. Size estimate: `XS` | `S` | `M` | `L` | `XL` — one-line rationale.
    - `XS` → suggest skipping plan, go straight to implement-task
    - `XL` → suggest splitting; list proposed sub-tasks
    - `S`–`L` → proceed to create-plan
