# TASK-016 implementation notes

## Manual AC smoke (7.2)

Marked N/A for live Redis/Tavily smoke in this run — no live services required by the plan; FR acceptance is covered by the automated suite (`537 passed` after review remediation).

## Notes for review / close

- Preference aliasing, host normalization, tool preparation, and profile-write canonicalization live in `ExecutionContextCore` (Core). `Agent` only orchestrates.
- New sessions default to `protocol_version=3` with persisted `request_constraints`; v1/v2 sessions load empty constraints and refresh recognized execution control messages on resume.
- No ADR candidate — decisions match the task design (Decisions 1–7).
- No tech-debt workarounds recorded.

## Review remediation

- Added direct/resume preference filtering, fixed-precedence prompt-contract, canonical-only Redis, strict no-results retry, and selection → recurring-job → dispatch → forced-execution coverage.
- Preserved scheduled `distilled_task` byte-for-byte and moved profile-value logging from INFO to DEBUG.
- Plan lesson: a green aggregate suite is not sufficient evidence for Stage 7.1; each named entry path and end-to-end FR chain must have a matching test before the step is checked.
- Second review remediation added direct selection-path coverage for immediate strict search, strict/soft/stored/default precedence contexts, and the one-off no-profile-write boundary.
- Plan lesson: asserting precedence headings in a skill prompt is weaker than exercising each tier through the Agent execution boundary.
