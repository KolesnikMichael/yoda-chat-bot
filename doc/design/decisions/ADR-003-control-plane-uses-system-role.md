---
id: ADR-003
title: "control plane uses system role"
date: 2026-07-22
created: 2026-07-22
tags:
  - agent
  - prompts
  - trust
---

# ADR-003: control plane uses system role

## Context

Skill catalogs, workflow instructions, validation feedback, and activation
rules are authoritative control-plane content. Mixing them with user tasks and
quoted conversation under the `user` role weakens authority and blurs trust
boundaries, inviting the model to treat instructions as negotiable or to treat
user text as control.

**Forces:**

- Multilingual user content and clarification answers must remain untrusted.
- Corrective retries need machine-generated feedback that is not user-authored.
- Synthetic assistant acknowledgements are a poor substitute for authoritative
  state.

## Decision

**Use the `system` role for control-plane messages:** classifier instructions,
selection contracts, skill activation, workflow instructions, validation
feedback, and other agent-initiated control content.

**Keep user-authored data in the `user` role:** original tasks, clarification
answers, and quoted conversation. Never promote user-authored text into
`system`. Do not insert synthetic assistant turns as a stand-in for control
state.

### Affected subsystems

- **ReactLoop message builders** — separate control vs payload messages.
- **Language / LLM calls** — phase prompts respect role split.
- **Delivery instructions** — code-owned rules stay outside untrusted data
  delimiters (see grounded-outcomes design).

## Rejected options

- **Single combined `user` message** (catalog + task + conversation) — blurs
  trust; weakens regression of control content.
- **Quote user text inside a system blob** — still risks instruction injection
  and mixes planes.

## Consequences

**Positive:**

- Clear trust model for prompts and for reviews of new skills/tools.
- Legacy session upgrades can refresh recognized control seeds without rewriting
  user-authored prefixes.

**Negative / accepted trade-offs:**

- Prompt builders must emit multiple messages per call.
- Resume/upgrade logic must structurally recognize generated control messages.

**Neutral:**

- Exact marker/delimiter strings are design/implementation detail; the role
  split is the policy.

## Related documents

- [[design/agent-two-phase-protocol|Agent two-phase protocol]]
- [[design/agent-skill-selection|Agent skill selection]]
- [[design/agent-grounded-outcomes|Agent grounded outcomes]]
