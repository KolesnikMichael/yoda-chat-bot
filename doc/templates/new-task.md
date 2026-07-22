<%*
// Next free TASK-NNN across active backlog/ and backlog/archive/ (folder names only).
const _idScan = (prefix, roots) => {
  const re = new RegExp("^" + prefix + "-(\\d+)");
  const used = new Set();
  let max = -1;
  const visit = (folder) => {
    if (!folder || !folder.children) return;
    for (const child of folder.children) {
      const m = child.name.match(re);
      if (m) {
        const n = parseInt(m[1], 10);
        used.add(n);
        if (n > max) max = n;
      }
      if (child.children) visit(child);
    }
  };
  for (const root of roots) visit(app.vault.getAbstractFileByPath(root));
  return { max, used };
};

const _taskIds = _idScan("TASK", ["backlog"]);
const suggested = String(_taskIds.max + 1);
const num  = await tp.system.prompt("Task number (next free: " + suggested + ")", suggested);
const name = await tp.system.prompt("Hyphenated name (e.g. skill-selection)");

if (!num || !name) { new Notice("Task creation cancelled."); return; }
if (!/^\d+$/.test(num.trim())) {
  new Notice("Task number must be digits only."); return;
}
const numInt = parseInt(num.trim(), 10);
if (_taskIds.used.has(numInt)) {
  new Notice("TASK-" + String(numInt).padStart(3, "0") + " already exists (active or archive).");
  return;
}

const epicFolder = (await tp.system.prompt("Epic folder or blank for a standalone task") || "").trim();
const epicMatch  = epicFolder.match(/^(EPIC-\d+)/);
const epic       = epicMatch ? epicMatch[1] : "";
const inEpic     = epic.length > 0;
const epicBranch = inEpic ? "feat/" + epicFolder : "";

const id    = "TASK-" + String(numInt).padStart(3, "0");
const folder = "backlog/" + id + "-" + name;
const title  = name.replace(/-/g, " ");
const today  = tp.date.now("YYYY-MM-DD");
const fence  = String.fromCharCode(96).repeat(3);

await tp.file.move(folder + "/task");

const requirements = [
  "---",
  "id: " + id,
  "doc: requirements",
  "updated: " + today,
  "---",
  "",
  "# " + id + ": " + title + " — Requirements",
  "",
  "← [[" + folder + "/task|Back to task]]",
  "",
  "## Context",
  "",
  "Why this task is needed. What problem it solves, for whom, under what conditions.",
  "",
  "## Functional requirements",
  "",
  "### FR-1: Requirement name",
  "",
  "Description: what exactly the system must do.",
  "",
  "**Acceptance criteria:**",
  "- [ ] Criterion 1",
  "- [ ] Criterion 2",
  "",
  "## Constraints & assumptions",
  "",
  "- **Constraint:**",
  "- **Assumption:**",
  "",
  "## Out of scope",
  "",
  "- "
].join("\n");

const design = [
  "---",
  "id: " + id,
  "doc: design",
  "updated: " + today,
  "---",
  "",
  "# " + id + ": " + title + " — Design",
  "",
  "← [[" + folder + "/task|Back to task]] | [[" + folder + "/requirements|Requirements]]",
  "",
  "## Solution overview",
  "",
  "One paragraph: the chosen approach and why this one.",
  "",
  "## Architecture",
  "",
  fence + "mermaid",
  "graph TD",
  "    A[Component A] --> B[Component B]",
  fence,
  "",
  "## Key decisions",
  "",
  "### Decision 1: Name",
  "",
  "**Context:** what problem we are solving.",
  "**Options:** Option A / Option B",
  "**Choice:** Option A, because...",
  "",
  "## Interfaces",
  "",
  "### API / Public contract",
  "",
  "Method signatures, tool schemas, or message contracts the implementer must follow.",
  "",
  "### Data model",
  "",
  fence,
  "Entity { id: str, field: str }",
  fence,
  "",
  "## System impact",
  "",
  "Table: file/class → IODA category → change → FR. This is the seed for the plan's «Files & artifacts».",
  "",
  "| Path / class | IODA | Change | FR |",
  "|--------------|------|--------|----|",
  "| <yoda/...> | Integration / Core / Provider / Portal / Data / API | create / edit / delete | FR-N |",
  "",
  "## Open questions",
  "",
  "- [ ] Question 1"
].join("\n");

const plan = [
  "---",
  "id: " + id,
  "doc: plan",
  "updated: " + today,
  "last_step: ",
  "branch: ",
  "---",
  "",
  "# " + id + ": " + title + " — Implementation plan",
  "",
  "← [[" + folder + "/task|Back to task]] | [[" + folder + "/requirements|Requirements]] | [[" + folder + "/design|Design]]",
  "",
  "## Overview",
  "",
  "One paragraph: what we build and why. Minimal context to grasp the task without opening task.md.",
  "",
  "## Goal / Non-goals",
  "",
  "- **Goal:** observable end state after the plan is executed.",
  "- **Non-goals:** what we explicitly do not do (from requirements Out of scope).",
  "",
  "## Context to load",
  "",
  "Files to read before starting:",
  "",
  "- [[" + folder + "/requirements|requirements]] — FR-1…FR-N and acceptance criteria",
  "- [[" + folder + "/design|design]] — «Architecture», «Interfaces», «System impact»",
  "- AGENTS.md (IODA + coding guidelines), coding_behavior.md",
  ...(inEpic ? ["- [[" + epicFolder + "/epic|" + epic + "]] + its master design — cross-task context (read first)"] : []),
  "- <!-- ADR-XXX, related TASK design.md, runbooks — as needed -->",
  "",
  "## Pre-flight",
  "",
  "Mandatory conditions before implementation starts.",
  "If any item below fails and cannot be satisfied immediately, do not proceed to implementation.",
  "",
  "- [ ] `git checkout main && git pull` — main is up to date",
  "- [ ] `git status` — working tree is clean",
  ...(inEpic
    ? ["- [ ] `git checkout " + epicBranch + " || git checkout -b " + epicBranch + "` — shared epic branch (created on the first task, reused afterwards)"]
    : ["- [ ] `git checkout -b <branch from frontmatter>` — feature branch created"]),
  "- [ ] `.venv` active and dependencies installed",
  "- [ ] Baseline tests green: `.venv/bin/python -m pytest`",
  "",
  "## Files & artifacts",
  "",
  "| Path | IODA | Op | FR |",
  "|------|------|----|----|",
  "| <yoda/path/to/file.py> | Integration / Core / Provider / Portal / Data / API | create / edit / delete | FR-N |",
  "",
  "## Stages",
  "",
  "### Stage 1: Name",
  "",
  "**Goal:** what is done after the stage.",
  "",
  "- [ ] **1.1** Short step name",
  "  - Files: <paths>",
  "  - Action: what exactly to do (cite IODA category + concrete symbols from design)",
  "  - Verify: for behavioral steps write the test first (red), then implement (green) — `.venv/bin/python -m pytest tests/test_x.py::test_y`",
  "  - Commit: `feat(" + id + "): 1.1 <subject>`",
  "",
  "- [ ] **1.2** Next step",
  "  - Files:",
  "  - Action:",
  "  - Verify:",
  "  - Commit: `feat(" + id + "): 1.2 <subject>`",
  "",
  "**Checkpoint Stage 1:** full suite green — `.venv/bin/python -m pytest`.",
  "",
  "---",
  "",
  "### Stage N: Test sweep & coverage",
  "",
  "- [ ] **N.1** Cover every FR's acceptance criteria with tests",
  "  - Files: tests/test_*.py (fakes in tests/fakes.py; mock API façades)",
  "  - Action: add/extend unit + integration tests for FR-1…FR-N",
  "  - Verify: `.venv/bin/python -m pytest`",
  "  - Commit: `test(" + id + "): N.1 <subject>`",
  "",
  "- [ ] **N.2** Manual AC check",
  "  - FR-1: <observable check>",
  "  - FR-2: <observable check>",
  "",
  "## Stage dependencies",
  "",
  fence + "mermaid",
  "graph LR",
  "    S1[Stage 1] --> S2[Stage N]",
  fence,
  "",
  "## FR coverage (traceability)",
  "",
  "| FR | Steps | Verification |",
  "|----|-------|--------------|",
  "| FR-1 | 1.1, N.1 | unit + manual |",
  "",
  "## Risks",
  "",
  "| Risk | Probability | Impact | Mitigation |",
  "|------|-------------|--------|------------|",
  "| | | | |",
  "",
  "## Rollback",
  "",
  "- Code: `git revert` the merge commit or reset the branch.",
  "- State: how to clear/restore Redis or ChromaDB entries if a step writes persistent state.",
  "",
  "## Definition of Done",
  "",
  "- [ ] All plan steps checked",
  "- [ ] All acceptance criteria from requirements.md pass",
  "- [ ] Full suite green: `.venv/bin/python -m pytest`",
  "- [ ] IODA + coding guidelines (AGENTS.md) respected",
  "- [ ] `review.md`: verdict `pass` or `pass-with-follow-ups`",
  "- [ ] `task.md`: `status: done`, `updated: <today>`",
  "- [ ] `design.md` / ADR updated if execution diverged from the plan",
  ""
].join("\n");

const review = [
  "---",
  "id: " + id,
  "doc: review",
  "updated: " + today,
  "verdict: ",
  "pytest: ",
  "---",
  "",
  "# " + id + ": " + title + " — Review",
  "",
  "← [[" + folder + "/task|Back to task]] | [[" + folder + "/plan|Plan]]",
  "",
  "Filled by **review-task**. Handoff to **implement-task** (`verdict: fix`) or **close-task** (`pass` / `pass-with-follow-ups` / `waived`).",
  "",
  "## Scope",
  "",
  "<!-- Diff summary: N files; key paths -->",
  "",
  "## FR matrix",
  "",
  "| FR | Code | Test | Status |",
  "|----|------|------|--------|",
  "| FR-1 | | | pass / weak / gap |",
  "",
  "## Findings",
  "",
  "<!-- One bullet per finding. Status: open | fixed. -->",
  "",
  "- [ ] **High/Medium/Low/Info** — `path` / symbol — why (FR-N / plan step) — `open`",
  "",
  "## Follow-ups",
  "",
  "<!-- For pass-with-follow-ups / Low-Info carry-overs for close-task -->",
  "",
  "- ",
  "",
  "## History",
  "",
  "| Date | Verdict | Note |",
  "|------|---------|------|",
  "| | | |"
].join("\n");

await tp.file.create_new(requirements, "requirements", false, folder);
await tp.file.create_new(design,       "design",       false, folder);
await tp.file.create_new(plan,         "plan",         false, folder);
await tp.file.create_new(review,       "review",       false, folder);

tR += [
  "---",
  "id: " + id,
  "epic: " + epic,
  'title: "' + title + '"',
  "status: todo",
  "priority: medium",
  "size: ",
  "created: " + today,
  "updated: " + today,
  "tags: []",
  "---",
  "",
  "# " + id + ": " + title,
  "",
  "## Description",
  "",
  "One paragraph: what needs to be done and why.",
  "",
  ...(inEpic ? [
    "## Epic",
    "",
    "Part of [[" + epicFolder + "/epic|" + epic + "]] — read the epic (decomposition, shared branch) and its master design first for cross-task context.",
    "",
    "## Master design",
    "",
    "<!-- Anchors this task implements, from epic decomposition (create-epic): -->",
    "- [[" + epicFolder + "/design#Section]]",
    "",
    "## Scope boundary",
    "",
    "**In scope:**",
    "- ",
    "",
    "**Out of scope:**",
    "- ",
    "",
  ] : []),
  "## Related documents",
  "",
  "- [[" + folder + "/requirements|requirements]] — requirements and acceptance criteria",
  "- [[" + folder + "/design|design]] — architectural solution",
  "- [[" + folder + "/plan|plan]] — implementation plan",
  "- [[" + folder + "/review|review]] — plan-compliance gate (verdict + findings)",
  ...(inEpic ? ["- [[" + epicFolder + "/epic|" + epic + "]] — epic decomposition and master design"] : []),
  "",
  "## Dependencies",
  "",
  "- Depends on: <!-- [[TASK-XXX]] -->",
  "- Blocks: <!-- [[TASK-XXX]] -->",
  "",
  "## Notes",
  "",
  "<!-- Short operational notes, decisions made on the fly -->"
].join("\n");
%>
