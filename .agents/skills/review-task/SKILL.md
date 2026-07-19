---
name: review-task
description: Plan-compliance gate after implement-task — diffs as-built code against implementatoin plan / requirements / design contracts / IODA, runs pytest, writes review.md (verdict + findings), and hands off to implement-task (fix) or close-task (pass). Use when the user asks to review, audit, gate, or check a backlog task against its plan; provides a task folder or task id (TASK-NNN). Part of the flow task → requirements → design → plan → implementation → review → close. It is designed to catch DoD blockers before status flips to done and to persist the gate result across context resets.
---

# Review Task

Gate between **implement-task** and **close-task**: verify the working tree matches
the implementation contract (`plan.md`, FR acceptance criteria, design interfaces,
IODA). 

Pipeline: requirements → design → plan → implement → **review** → close.

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to task folder (e.g. `doc/backlog/TASK-008-summary-store-and-outbox-flush/`) | Read `plan.md`, `requirements.md`, `design.md`, `task.md`, `review.md`, `implementation-notes.md` |
| Task id (`TASK-008`, `008`, `8`) | Find folder: `doc/backlog/TASK-{NNN}-*/` (zero-pad to 3 digits) |
| «review TASK-NNN» / «проверь задачу N» | Same as task id |

If multiple folders match or none exist, stop and ask.

```bash
ls -d doc/backlog/TASK-{NNN}-*   # substitute the zero-padded id, e.g. TASK-008
```

## Prerequisites

1. **`plan.md`** exists and steps are claimed complete (all `- [x]` in Stages, or
   user asks for a mid-task review of current progress — then scope to checked
   steps only and say so in `review.md`).
2. Root `AGENTS.md` (IODA + coding guidelines) and `coding_behavior.md` are in mind.
3. No code/test edits; no commits; no `task.md` status flips. If findings need
   fixes → set `verdict: fix` in `review.md` and advise the user to run
   **implement-task** again.

### Skip (user may waive the gate)

Offer skip only when the user asks, or when clearly appropriate:

- Task size `XS` and docs-only / no production code under `yoda/`
- User explicitly: «close without review» / «skip review-task»

Write `review.md` with `verdict: waived`, a one-line reason, and `updated: <today>`
so **close-task** can proceed without re-asking.

## Documentation map

| File | Role |
|------|------|
| `plan.md` | **Primary contract** — Files & artifacts, Stages, FR coverage table, Definition of Done, Non-goals |
| `requirements.md` | FR-N acceptance bullets (spot-check; prefer plan FR table when aligned) |
| `design.md` | **Interfaces** + **Key decisions** + flush/reconcile pseudocode only — do not re-read the whole vault |
| `implementation-notes.md` | Known divergences / workarounds (absent = assume clean run) |
| `review.md` | **Output** — verdict, FR matrix, findings, follow-ups, history (handoff) |
| `git diff` + untracked | As-built evidence |

## `review.md` contract

Frontmatter (required after a run):

```yaml
---
id: TASK-NNN
doc: review
updated: YYYY-MM-DD
verdict: pass | pass-with-follow-ups | fix | waived
pytest: pass | fail | skipped
---
```

Body sections (keep filled, replace stub placeholders):

| Section | Content |
|---------|---------|
| **Scope** | Diff summary (file count + key paths) |
| **FR matrix** | FR / Code / Test / Status (`pass` \| `weak` \| `gap`) |
| **Findings** | Bullets: severity — path/symbol — why (FR/plan ref) — `open` \| `fixed` |
| **Follow-ups** | Low/Info or waived Medium for **close-task** |
| **History** | Append one row per review run: date, verdict, short note |

On **re-review**: refresh frontmatter + FR matrix + findings (mark fixed items
`fixed`; leave unresolved `open`); **append** a History row — do not delete prior
rows.

## Workflow

Copy and track:

```
- [ ] Task folder resolved; plan + FR table + design Interfaces loaded
- [ ] Diff scope listed (modified + untracked vs plan Files & artifacts)
- [ ] FR matrix filled (code + test evidence)
- [ ] IODA + coding-guideline pass
- [ ] Design contracts / Non-goals checked
- [ ] Full pytest green (or justified skip)
- [ ] review.md written (verdict + findings + History row)
- [ ] Verdict and findings briefly reported in chat, next skill advised
```

### 1. Scope the diff

```bash
git status
git diff --stat
# include untracked files that belong to the task (new modules/tests)
```

Compare paths to `plan.md` **Files & artifacts**. Note: missing planned files,
unexpected extra files, and doc-only churn.

### 2. FR matrix

Walk `plan.md` **FR coverage (traceability)** (fallback: `requirements.md` FR-N).
For each FR:

| Column | Meaning |
|--------|---------|
| FR | id |
| Code | where behaviour lives (file/symbol) |
| Test | automated test name(s) or `manual` / `gap` |
| Status | `pass` / `weak` / `gap` |

**`weak`** = behaviour roughly present but the test does not match the acceptance
bullet (e.g. happy-path retry instead of fail-after-persist). Treat **High**
severity `weak`/`gap` on core FRs as blocking unless the user waives.

### 3. IODA + coding guidelines

Against root `AGENTS.md` and the implement-task checklist:

- Each new/changed class is one IODA category with correct naming.
- Operations (**Core / Provider / Portal**) do **not** import or call other
  Operations or Integrations; Integration orchestrates and passes data.
- No Provider→Provider calls; API façades only at the edge.
- Fail-fast validation; `logger.debug` for user data; type hints; `@staticmethod`
  where appropriate.

### 4. Design contracts and Non-goals

- Compare design **pseudocode / Interfaces** for touched Integrations/Providers
  to the implementation (order of calls, clear-on-success-only, startup vs tick).
- Confirm `plan.md` **Non-goals** / requirements **Out of scope** were not
  implemented by accident (`search`, stash-on-flush, etc.).

### 5. Tests

```bash
.venv/bin/python -m pytest
```

Suite must be green for `pass`. If red → `verdict: fix` (`pytest: fail`).
Do not mark FR `pass` solely because a related file exists — name the test.

### 6. Severity, verdict, write `review.md`

Classify each finding:

| Severity | Examples | Blocks close? |
|----------|----------|---------------|
| **High** | IODA Operation→Operation dep; missing FR behaviour; red suite | Yes |
| **Medium** | FR test weaker than acceptance; missing metadata/assert called out in plan | Usually yes for core FRs |
| **Low** | Style, helper kwargs, doc drift already noted for close-task | No — follow-up OK |
| **Info** | Pin vs minimum dependency; known deferred follow-up | No |

**Verdict (exactly one in frontmatter):**

| Verdict | When | Next step |
|---------|------|-----------|
| `pass` | No High/Medium blockers | **close-task** |
| `pass-with-follow-ups` | Only Low/Info; optional Medium waived by user | **close-task**; list in Follow-ups |
| `fix` | High or unwaived Medium | **implement-task** (fix open findings), then re-run **review-task** |
| `waived` | User skipped the gate | **close-task** |

Write/update `review.md`, then mirror a short report in chat.

Do **not** flip `task.md` `status: done` here.

## Do not

- Edit production code or tests (only `review.md` may be written)
- Flip `task.md` / epic status or create ADR/follow-up task files
- Re-read the entire vault / epic master design unless a finding forces it
- Call Bugbot / security-review unless the user explicitly asks
- Treat implement-task’s self-check as a substitute for this gate
- Rely on chat alone for the verdict — **`review.md` is the source of truth**

## Output

Chat report (short), mirroring `review.md`:

1. **Task id** + path to `review.md`
2. **Verdict** + `pytest` from frontmatter
3. **Findings** summary (open High/Medium count; link to file for detail)
4. **Next step**: `close-task` / `implement-task` (fix open findings) then re-review / waiver noted
