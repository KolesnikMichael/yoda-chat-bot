---
title: "agent execution constraints"
updated: 2026-07-22
tags:
  - agent
  - preferences
  - constraints
---

# Agent execution constraints

Durable contract for skill-scoped preferences versus per-request source
constraints. Historical source: TASK-016 (EPIC-002 Decision 4).

Related: [[design/agent-two-phase-protocol|two-phase protocol]],
`ExecutionContextCore` in `yoda/mind/agent/core/execution_context.py`.

## Preferences versus request constraints

| Kind | Lifetime | Role |
|------|----------|------|
| Stored `skill_preferences` | Profile | Defaults for the **active** skill only |
| `RequestConstraints` | This task / job | Mechanical strict/soft source domains |
| `distilled_task` | This task / job | Human-readable self-contained work statement |

Precedence for executor behavior:

1. Explicit **strict** request constraint  
2. Explicit **soft** request preference  
3. Stored active-skill preference  
4. Skill default  

A one-off source request is **not** promoted to a durable profile preference
unless the user states a lasting choice and execution calls `update_profile`.

`RequestConstraints` travel beside the distilled task (sidecar). They do not
replace it. Selection must still mention entities, language, output needs, and
strict/soft choices in `distilled_task`.

## Data shape

```python
class RequestConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strict_source_domains: list[str] = Field(default_factory=list)
    soft_source_domains: list[str] = Field(default_factory=list)
```

- Carried on `SelectionDecision`, `AgentContext`, suspended sessions, and
  dynamic-job payloads (`protocol_version=3+`).
- Missing sidecar → empty constraints (legacy jobs/sessions).
- A host cannot stay in both lists: **strict wins**.

## ExecutionContextCore

Pure synchronous Core — no I/O, no calls to other Operations.

| Method | Responsibility |
|--------|----------------|
| `effective_skill_preferences` | Active skill list only; for `search_web`, emit canonical values then legacy `web_search` with case-insensitive dedupe |
| `normalize_request_constraints` | Host normalize; strict/soft conflict resolution |
| `prepare_tool_requests` | Enforce strict domains before dispatch |
| `canonicalize_profile_update_fields` | Map `web_search` → `search_web` on writes |

### Strict domain enforcement

For a non-empty strict list, before any tool runs:

- `web_search`: inject exact `include_domains` when absent; accept an existing
  list only if set-equal to the restriction; otherwise → protocol issue, no
  dispatch.
- `web_extract`: URL host must equal or be under an allowed host.
- `schedule_task`: receive current typed constraints from Core (do not trust
  the model to copy them).

Soft domains and stored preferences are **not** injected into
`include_domains`; they guide the workflow/prompt only. Prompt `site:` syntax
alone is not enforcement. If allowed domains yield nothing usable, report the
limitation — do not silently widen.

### Host normalization

Accept bare hosts and `http`/`https` URL-like input → hostname, lowercase,
IDNA, strip trailing DNS dot. Reject credentials, wildcards, leading dots,
unsupported schemes, IP literals, invalid labels. **Do not** strip `www`,
collapse to parent domain, or broaden the host.

## Preference key canonicalization

- Canonical skill key: `search_web` (not tool name `web_search`).
- New writes (summarizer + agent `update_profile`) canonicalize to `search_web`.
- Reads merge legacy `web_search` without rewriting Redis.
- Selection still uses general profile context **without** skill preferences.

## Trust boundaries in prompts

Execution `system` context may include a JSON
`<profile_data trust="untrusted">` block (common fields + active preference
list) with an explicit “data, not control” rule. Task + normalized constraints
stay in a separate `user` message.

## Code map

| Concern | Location |
|---------|----------|
| Core policy | `yoda/mind/agent/core/execution_context.py` |
| Dispatch prep | `Agent` after execution validation |
| Persisted job sidecar | `schedule_task` tool / job JSON |
| Preference writes | `update_profile` tool + summarizer |

## Historical

- [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/design|TASK-016 design]]
