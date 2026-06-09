# Implement Task

Execute `plan.md` for a backlog task. This skill continues the agent pipeline: create `requirements.md` → create `design.md` → create `plan.md` → **implement plan**.

The plan holds **what** to do (steps, verify, files). This skill holds **how the agent must behave** (pre-flight gate, resume, checkpoints, DoD).

## Input (resolve first)

The user may pass **one** of:

| Input | Resolution |
|-------|------------|
| Path to `plan.md` | Task folder = parent directory |
| Path to task folder (e.g. `doc/backlog/TASK-007-skill-selection/`) | Read `plan.md` inside |
| Task id (`TASK-007`, `007`, `7`) | Find folder: `doc/backlog/TASK-{NNN}-*/` (zero-pad to 3 digits) |
| «Реализуй задачу N» / «implement TASK-NNN» | Same as task id |

If multiple folders match or none exist, stop and ask.

```bash
ls -d doc/backlog/TASK-007-*
```

## Prerequisites

Before any code change:
1. Check that **`plan.md`** exists and is filled (not template placeholders like `<path/to/file>`). If **`plan.md` is missing or stub** — STOP; ask the user to complete the **plan** stage first (`create-plan`).
2. Read the root `AGENTS.md` (IODA architecture + coding guidelines + test command), `doc/AGENTS.md`, and `coding_behavior.md`.

## Phase 0 — Pre-flight

⛔ **Do not edit repository code** until all the steps in this phase pass unless the user explicitly approves skipping a step.

### Step 1: Prepare your workplace

Use the following git protocol:

```bash
git checkout main && git pull
git status   # must be clean — if not, STOP and ask user
```

**Resolve the branch (epic takes precedence):**

- If `task.md` has `epic: EPIC-NNN` → use the **shared epic branch** from `EPIC-NNN-*/epic.md` `branch:` (`feat/EPIC-NNN-slug`). Do **not** create a per-task branch. Create it only if it does not exist yet (first task of the epic); otherwise check it out and continue committing on it:

  ```bash
  git checkout <epic branch> 2>/dev/null || git checkout -b <epic branch>
  ```

- Otherwise (standalone task) → read `branch:` from `plan.md`. If empty, **fill it** first (pattern: `feat/TASK-NNN-short-slug`, match the task folder name), then:

  ```bash
  git checkout -b <branch from plan frontmatter>
  ```

If already on the correct branch with the task's (or epic's) commits and the user is resuming, skip recreate but still verify `git status`. On a shared epic branch, expect prior member-task commits to be present — that is normal, not a dirty tree.

### Step 2: Validate `plan.md`

Verify that the plan is still current and applicable to the repository's present state. Confirm that all files, directories, and modules listed in the **Files & artifacts** section exist and match the repository structure.

If any referenced artifact is missing, renamed, relocated, or otherwise inconsistent with the plan — **STOP**; report which item is inconsistent and the probable cause.

### Step 3: Execute task-specific pre-flight checks

Execute **every** checklist item in `plan.md` **Pre-flight** (`.venv` active, dependencies installed, API keys/services for LLM·Telegram·Redis·ChromaDB·Tavily·speech, seed data, baseline tests). The baseline gate is:

```bash
.venv/bin/python -m pytest
```

If a required key, service, or dependency is unavailable — **STOP**; report which item failed and what is needed.

### Step 4: Update plan frontmatter on first start

When pre-flight passes and work begins:

```yaml
status: in-progress
started: YYYY-MM-DD
branch: feat/TASK-NNN-...
last_step:    # keep empty until first step completes
```

Set `task.md` `status: in-progress` if still `todo`.

## Phase 1 — Load execution state

Read in order:

1. `plan.md` — **Overview**, **Files & artifacts**, **Stages**, **Definition of Done**
2. `last_step` in frontmatter — resume point (empty = start at first step)
3. **Context to load** in plan — load listed files only; do not re-read the entire vault
4. `requirements.md` / `design.md` — only sections needed for the current step

## Phase 2 — Execute plan steps

### Step loop

For each step `N.M` in **Stages** (in order, skip steps before `last_step` when resuming):

1. Read nested **Files / Action / Verify / Commit**
2. Implement **Action** — surgical changes per `coding_behavior.md`; touch only listed files; respect the step's IODA category and Yoda coding guidelines (see checklist below)
3. **TDD:** for any step that changes behavior, write the failing test first (red), then implement until the test passes (green). The step's **Verify** names that test.
4. Run **Verify** — command or observable check; do not check the box if Verify fails (see **Verify failure** below)
5. Update `plan.md`: check `- [ ] **N.M**` → `- [x]`, set `last_step: N.M`
6. **Commit** — only if the user asked to commit, or project rules require it; otherwise leave changes for the user. Proposed message is in the **Commit:** field (`feat(TASK-NNN): N.M …`)

After the last step of each stage, run that stage's **Checkpoint** verification before proceeding.

### IODA + coding-guideline checklist (apply to every code step)

- Class lands in exactly one IODA category and is named accordingly (`*Core`, `*Provider`, `*Portal`, bare-noun Integration, DTO Data).
- Operations (Core/Provider/Portal) do not depend on other Operations or Integrations; the Integration passes data between them as parameters.
- `@staticmethod` on methods that don't need instance state; explicit type hints on every function/method; f-strings for concatenation.
- Fail fast on config/validation — no lenient fallbacks.
- `logger.debug` for anything with user data (messages, profile, jobs).
- `asyncio.gather()` when 2+ Providers/Portals have independent inputs.
- Side effects sit behind API façades (mocked in tests via `tests/fakes.py`).

### Rules during execution

- **No scope expansion** — only steps and FRs in the plan
- **No parallel skipping** — respect stage dependencies (mermaid in plan)
- Follow design contracts; no breaking changes unless plan says so
- Do **not** edit `requirements.md` or `design.md` unless user asks or DoD requires ADR/design update

### Verify failure

If a step's Verify fails:
1. Do not check the step box.
2. Do not proceed to the next step.
3. Attempt to fix within the same step scope (files listed in that step only).
4. If not fixable without touching other steps' files — stop and report:
   - which step failed
   - what Verify produced
   - whether rollback to the stage Checkpoint is needed

To rollback to the last Checkpoint:
- `git stash` or `git checkout -- <files>` for a targeted code revert
- Clear/restore any persistent state the step wrote (Redis keys, ChromaDB entries) per the plan's **Rollback**
- Re-run Checkpoint verification to confirm a clean state

### Resume after interruption

If `last_step: 3.2`, next step is the following unchecked `N.M` after 3.2. Re-run pre-flight git checks if unsure about branch/state.

## Phase 3 — Close (plan Definition of Done)

When all plan steps are checked:

1. **Tests close-out (mandatory):** ensure every FR's acceptance criteria is covered by a test in `tests/`. Add or extend `test_*.py` (use `tests/fakes.py` to mock API façades) for any FR not yet exercised, then run the full suite green:

   ```bash
   .venv/bin/python -m pytest
   ```

   Do not mark the task done while the suite is red or an FR lacks a covering test.
2. Run the remaining plan **Definition of Done** items (IODA/coding-guideline review, manual AC, docs).
3. Mark FR acceptance criteria mentally or in the report — do not edit requirements checkboxes unless the user asks.
4. `plan.md`: `updated: <today>` — if plan DoD requires it.
5. If any of the following occurred, create `implementation-notes.md` in the task folder and record the incident:
    - a step failed or had to be reworked — note what the plan got wrong and how it should have been written.
    - a workaround was used — note what was done, why, and when it should be revisited (`tech-debt: <condition>`).
    - something discovered during implementation affects `design.md` or architecture — note the signal and which document needs updating.
    - a decision made during implementation has cross-task or architectural reach — flag it as an **ADR candidate**.

   These notes are the input for a postmortem pass (ADR creation, follow-up tasks, design reconciliation).

Report briefly:

- Task id, branch name
- Steps completed (`last_step`)
- Verify results (full `pytest` run, manual AC)
- Open items / deferred follow-ups
- Items from `implementation-notes.md` (incl. ADR candidates)

## Do not

- Start coding on `main` without a pre-flight branch
- Ignore failed Verify and check the step anyway
- Replace plan steps with ad-hoc implementation
- Commit unless the user requested (atomic **Commit:** lines are proposals)
- Mark plan/task done while tests fail, an FR is uncovered, or DoD items are open
- Violate IODA placement or naming for expedience
