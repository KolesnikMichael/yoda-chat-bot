---
id: ADR-002
title: "agent orchestration is an Integration"
date: 2026-07-22
created: 2026-07-22
tags:
  - agent
  - ioda
---

# ADR-002: agent orchestration is an Integration

## Context

Agent work spans phase transitions, session suspend/resume, tool dispatch, and
terminal assembly. Under IODA, that coordination belongs to an Integration, not
a Provider. A historical `AgentProvider` mixed orchestration with the Provider
naming/convention, which invited business policy and multi-Operation dependencies
into the wrong layer.

**Forces:**

- Phase validation, preference/constraint policy, scheduling validation, and
  outcome/delivery policy must stay in pure Cores.
- Tools and session/language adapters must remain independently testable without
  depending on other Operations.
- Callers (`Mind`, job dispatcher) need a single async entry surface.

## Decision

Own agent orchestration in a bare-noun **`Agent` Integration**
(`yoda/mind/agent/agent.py`). Keep transition/validation policy in Core
(`ReactLoop` and sibling Cores). Keep infrastructure adaptation in narrowly
scoped Providers and tool ports. Do not reintroduce a Provider façade that
coordinates phases or other Operations.

### Affected subsystems

- **Mind** — injects and calls `Agent`; does not own phase state.
- **Agent module** — Integration + Core + Provider/tool boundaries as in module
  `AGENTS.md`.
- **Wiring** — constructs `Agent` from independent Operations and tool ports.

## Rejected options

- **Keep `AgentProvider` as orchestrator** — violates IODA Provider constraints;
  hides Integration responsibility behind a misleading name.
- **Shim `AgentProvider` delegating to `Agent`** — unnecessary when all callers
  are in-repo and the external contract is persisted data, not Python imports.

## Consequences

**Positive:**

- Clear review gate: policy in Core, side effects in tools/Providers, wiring in
  Integration.
- Matches project-wide IODA naming and dependency rules.

**Negative / accepted trade-offs:**

- Call sites and tests must use `Agent`, not a Provider name.
- Future refactors must not grow business rules inside `Agent` methods.

**Neutral:**

- Exact file layout of sibling Cores can evolve; the Integration boundary does
  not.

## Related documents

- [[design/decisions/ADR-000-sensitive-data-persistence|ADR-000]]
- [[design/agent-two-phase-protocol|Agent two-phase protocol]]
