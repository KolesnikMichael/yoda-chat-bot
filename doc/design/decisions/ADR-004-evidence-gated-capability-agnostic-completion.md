---
id: ADR-004
title: "evidence-gated capability-agnostic completion"
date: 2026-07-22
created: 2026-07-22
tags:
  - agent
  - outcomes
  - safety
---

# ADR-004: evidence-gated capability-agnostic completion

## Context

Free-form model finishes and human-readable tool strings can claim side effects
that did not occur. Internal phase/schema/provider errors, if leaked into the
companion path, invite improvised recovery or disclosure of implementation
details. User-visible completion must stay truthful and safe across chat,
resume, and scheduled job paths.

**Forces:**

- Probabilistic rendering (language, Yoda voice) is still desired after policy
  fixes meaning.
- Static scheduled messages and dynamic scheduled tasks must not share claims.
- Failures should guide the user (clarify, retry later, capability boundary)
  without exposing internals.

## Decision

1. **Evidence-gated success** — authorize terminal success only from
   code-derived typed evidence / terminal tool facts. A model `finish` may
   summarize; it must not choose operation, result kind, job kind, or failure
   category. An evidence-free finish is a safe failure, not “completed”.

2. **Capability-agnostic safe failures** — user-visible failures use a closed
   category set (ambiguous / transient / unsupported) and fixed next-step
   dispositions. Do not surface skill, tool, model, schema, phase, storage, or
   provider details.

3. **Claim-bounded delivery** — Core derives allowed/prohibited claim tokens;
   the renderer may rephrase inside those bounds but must not strengthen facts
   or imply unproven side effects.

### Affected subsystems

- **Outcome and delivery Cores** — authorize outcomes and build instructions.
- **Agent / Mind / JobDispatcher** — pass Data; do not invent success from prose.
- **Terminal tools** — attach typed facts only after successful side effects.
- **Logging** — categories/enums at INFO; task text and tool output DEBUG-only
  (align with ADR-000).

## Rejected options

- **Trust non-empty model finish as success** — ungrounded claims.
- **Parse operation/job kind from display text** — brittle and forgeable.
- **Expose internal error strings to the companion model** — leakage and
  unsafe improvisation.

## Consequences

**Positive:**

- Direct, resume, and forced-skill paths share one comparable result contract.
- Static vs dynamic job claims stay distinguishable at creation and trigger time.
- Reviews have a clear gate: “what evidence authorizes this claim?”

**Negative / accepted trade-offs:**

- More structured Data and Core policy than a single answer string.
- Legacy sessions without typed evidence cannot finish until new successful
  results accumulate.

**Neutral:**

- Exact enum member lists and claim token names live in the grounded-outcomes
  design and code; this ADR freezes the policy, not the vocabulary.

## Related documents

- [[design/decisions/ADR-000-sensitive-data-persistence|ADR-000]]
- [[design/agent-grounded-outcomes|Agent grounded outcomes]]
- [[design/agent-two-phase-protocol|Agent two-phase protocol]]
