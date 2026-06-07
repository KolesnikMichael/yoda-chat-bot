# Requirements review checklist

Apply **before** writing or finalizing `design.md`. For each dimension, mark **Pass**, **Gap**, or **Conflict** and note evidence (FR id, quote, or doc link).

## Dimensions

### 1. Completeness

- Every goal in `task.md` **Description** maps to at least one FR.
- Actors, surfaces (private/group chat, scheduled jobs, voice/photo intake, admin), and error cases are covered.
- Dependencies (`[[TASK-XXX]]`) are reflected (extend vs replace behavior).
- **Out of scope** in requirements matches `task.md` and does not hide in-scope work.
- Non-functional needs (latency, cost/budget, rate limits, logging, persistence) appear if the task implies them.

**Gap signals:** vague FR, missing AC for an edge case, behavior change without group-chat rules, persistence change without cleanup rules.

### 2. Feasibility

- FRs fit the current stack (Python 3.12, asyncio, Telegram bot, Redis, ChromaDB, LLM/Tavily/speech APIs).
- Contract/persistence changes are proportionate; no impossible constraints.
- Cross-task prerequisites are **done** or explicitly deferred with a viable workaround.
- Code spot-check confirms referenced components exist or extension points are clear.

**Gap signals:** FR requires a greenfield subsystem not in scope; persistence change contradicts existing data model.

### 3. Testability

- Each acceptance criterion is **pass/fail** without subjective judgment.
- Criteria name observable outcomes (reply sent, tool invoked, intent classified, Redis/Chroma entry written, log line emitted).
- No weak wording: "correctly", "conveniently", "works as expected" without a measurable definition.

**Gap signals:** AC duplicates FR prose without verifiable checks; missing negative cases (no reply, validation error, API failure path).

### 4. Consistency

- FRs do not contradict each other.
- Requirements align with `task.md` (scope, terminology).
- No conflict between FRs and linked ADRs / design docs.
- Dependency task requirements are explicitly superseded or extended, not silently ignored.

**Conflict signals:** FR-7 changes a contract that FR-5 still assumes in its old form without resolution.

### 5. Alignment with project design

- Respects ADRs in `doc/design/decisions/`.
- Fits `doc/design/` boundaries and naming.
- Reuses patterns from related task `design.md` and existing modules.
- New cross-cutting decisions flagged for ADR if they affect multiple tasks.

**Gap signals:** new contract style unlike existing modules; behavior that conflicts with a documented design doc.

### 6. IODA compliance

- New/changed classes map cleanly to exactly one IODA category (Integration / Core / Provider / Portal / Data / API) per the root `AGENTS.md`.
- Naming convention holds: `*Core` (sync, pure logic), `*Provider` (async infra), `*Portal` (async user-facing), bare noun for Integration, DTOs for Data.
- Hard rules hold: Operations (Core/Provider/Portal) never depend on other Operations or Integrations; if Operation A needs data from Operation B, the Integration passes it as a parameter.
- Side-effecting work sits behind an API façade (mockable in tests), not inside Core.

**Gap signals:** business logic landing in an Integration; a Provider importing another Provider; a `*Core` doing async I/O; an API call made directly from Core.

### 7. Traceability

- Each FR-N has a clear design hook (data model, interface, behavior, persistence).
- Acceptance criteria can be verified from design artifacts (contract snippet, field list).
- Open questions in requirements are answered or listed in design **Open questions**.

### 8. Unambiguity

- Terms defined once.
- Defaults stated (optional fields, fallback behavior, error path).
- Backward compatibility explicitly specified where FRs mention legacy/stored behavior.

### 9. Plan-readiness

Apply at the **end** of design work, before declaring `design.md` ready for `create-plan`.

- «System impact» contains concrete paths/classes **with IODA categories** (not vague phrases like "mind changes", "memory updated").
- Each FR-N has at least one artifact in the impact table — otherwise the plan cannot derive steps.
- «Open questions» = `None.` or marked non-blocking with the FRs/steps they do not affect.
- Interface snippets are concrete (no `Component A`, `Option A`, `field: str` without fields).
- Persistent-state / rollout / rollback considerations are implied or explicitly recorded (needed for `Pre-flight` and `Rollback` in plan).

**Gap signals:** "backend changes" as one impact row; "align with the team" in Open questions without owner; FR without a matching impact row; decorative snippet without a concrete contract.

## Review output template

Use in chat before filling design:

| Dimension | Status | Notes |
|-----------|--------|-------|
| Completeness | Pass / Gap / Conflict | |
| Feasibility | … | |
| Testability | … | |
| Consistency | … | |
| Alignment with project design | … | |
| IODA compliance | … | |
| Traceability | … | |
| Unambiguity | … | |
| Plan-readiness | … | only when finalizing `design.md` |

**Actions:**

- **Gap** → ask user or suggest FR patch (do not edit `requirements.md` unless asked).
- **Conflict** → resolve with user; record in design **Decisions made**.
- All **Pass** (1–8) → proceed to fill `design.md`.
- **Plan-readiness Pass** → `design.md` ready to hand off to `create-plan`.
