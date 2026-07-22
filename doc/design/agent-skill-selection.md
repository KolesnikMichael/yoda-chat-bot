---
title: "agent skill selection"
updated: 2026-07-22
tags:
  - agent
  - skills
  - selection
---

# Agent skill selection

Durable contract for discriminative catalog metadata and selection prompts.
Historical source: TASK-014 (specializes EPIC-002 selection vs execution and
static vs dynamic concepts).

Related: [[design/agent-two-phase-protocol|two-phase protocol]],
[[design/decisions/ADR-003-control-plane-uses-system-role|ADR-003]],
skill files under `yoda/mind/agent/skills/specs/`.

## Selection contract versus execution workflow

| Phase | Sees | Does not see |
|-------|------|----------------|
| Selection | Compact `SkillSummary` contracts (all skills, including `public: false`) | Tool schemas, full workflow body, profile skill preferences |
| Execution | Full `SkillSpec` workflow, filtered tools, active preferences | Sibling skills' preference maps |

Public chat CAPABILITIES still use `description` + `public`; selection uses
separate discriminative fields. Catalog load **fail-fast** if any current spec
omits or malforms selection fields (no description fallback).

## Required frontmatter fields

Every `skills/specs/*.md` must declare:

```yaml
name: schedule_message
description: Schedule a reminder message for later delivery.  # public view
public: true
purpose: Deliver static user-specified text at a later time.
when_to_use:
  - The payload is known when the job is created and should be delivered later.
do_not_use_when:
  - The payload requires fresh data, search, computation, or monitoring at trigger time.
selection_examples:
  - '"Every day at 9 remind me to take vitamins" -> use'
  - '"Every day at 9 send fresh weather" -> do not use; search_web'
```

Workflow headings and body examples are never inferred into the selection
contract.

## Static message versus dynamic task

- **Static message** (`schedule_message`) — deliver stored text later; must not
  claim live lookup/recompute at trigger time.
- **Dynamic task** (`schedule_task` + skill such as `search_web`) — run the
  skill at trigger time and produce fresh output.
- **Recurrence is not the discriminator** — both kinds can recur; whether the
  payload must be recomputed at fire time is.

## Serialization invariants

- Contracts rendered **sorted by skill `name`** with fixed field order:
  `name`, `purpose`, `when_to_use`, `do_not_use_when`, `selection_examples`.
- Catalog order carries **no semantic priority** (explicit rule in the prompt).
- Selection emits `system` (catalog + rules) then `user` (conversation + task).
- On activation, workflow/tools/instruction → `system`; distilled task → `user`.
  No synthetic assistant acknowledgement.

## Legacy sessions

Pre-selection Redis payloads may lack selection fields (empty defaults on
decode). Before the next selector call, `Agent` replaces `catalog_summaries`
with the current validated catalog and refreshes only the recognized selection
seed; user-data prefix and later messages stay intact. Unrecognized shapes
fail rather than risk promoting or deleting user data.

## Code map

| Concern | Location |
|---------|----------|
| Spec discovery / validation | `yoda/mind/agent/skills/catalog.py` |
| Selection message build | `yoda/mind/agent/core/react_loop.py` |
| `SkillSummary` Data | `yoda/mind/agent/data/agent_data.py` (and skill types) |
| Spec files | `yoda/mind/agent/skills/specs/*.md` |

## Historical

- [[backlog/archive/TASK-014-discriminative-skill-selection-contracts/design|TASK-014 design]]
- [[backlog/archive/EPIC-002-agent-routing-reliability/design|EPIC-002 master design]]
