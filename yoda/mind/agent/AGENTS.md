# Agent Module

Two-phase ReAct loop with declarative skills and typed tools.

Code conventions: [../../../AGENTS.md](../../../AGENTS.md)  
Protocol design (source of truth):
[EPIC-002 master design](../../../doc/backlog/EPIC-002-agent-routing-reliability/design.md)

## Layout

```
yoda/mind/agent/
  agent.py                # Integration — phase orchestration, tool dispatch
  session_provider.py     # Provider — Redis session persistence
  core/
    react_loop.py         # Core — context building, decision validation, corrections
    execution_context.py  # Core — preference aliasing, constraint preparation
    outcome_core.py       # Core — evidence gating, safe failure mapping
    delivery_core.py      # Core — grounded delivery payload for Mind
    schedule_core.py      # Core — timezone validation, schedule resolution
  data/
    agent_data.py         # Data — AgentContext, phase decisions, protocol types
    outcome_data.py       # Data — ExecutionOutcome, evidence, delivery payloads
  skills/
    catalog.py            # startup adapter — auto-discovers specs/
    specs/*.md            # declarative skill definitions
  tools/
    tool_port.py          # Tool ABC + ToolCall contract
    *_tool.py             # Tool implementations (injected at wiring)
```

## IODA map

| Component | Category | Responsibility |
| `Agent` | Integration | Calls Cores and Providers; no business logic |
| `ReactLoop` | Core | Phase context, validation, corrective retries |
| `ExecutionContextCore` | Core | Preference reads/writes, pre-dispatch constraints |
| `OutcomeCore` | Core | Evidence gating, failure categories |
| `DeliveryCore` | Core | Allowed/prohibited claims for Mind delivery |
| `ScheduleCore` | Core | IANA timezone validation |
| `AgentSessionProvider` | Provider | Suspend/resume persistence |
| `SkillCatalog` | Provider adapter | Load skill specs from disk |
| `*Tool` | Tool port | Stateless side effects; receive `ToolCall` only |
| `agent_data` / `outcome_data` | Data | Contracts and context |

Injected at wiring: `LanguageProvider` (perception), `MemoryProvider` (via profile
tools), APIs inside individual tools.

## Where to look

| Question | Go to |
| Two-phase protocol, stage correctness | [EPIC-002 design](../../../doc/backlog/EPIC-002-agent-routing-reliability/design.md) |
| Phase protocol, suspend/resume | [TASK-015 design](../../../doc/backlog/TASK-015-phase-protocol-and-agent-integration/design.md) |
| Preferences vs request constraints | [TASK-016 design](../../../doc/backlog/TASK-016-execution-preferences-and-domain-constraints/design.md) |
| IANA timezone execution | [TASK-017 design](../../../doc/backlog/TASK-017-iana-timezone-execution-guidance/design.md), `skills/specs/schedule_message.md` |
| Grounded outcomes, delivery | [TASK-018 design](../../../doc/backlog/TASK-018-grounded-outcomes-and-safe-failures/design.md) |
| Routing evaluation (CI + live) | [evaluation/AGENTS.md](../evaluation/AGENTS.md), [live-routing-eval runbook](../../../doc/runbooks/live-routing-eval.md) |
| Skill workflow details | `skills/specs/<name>.md` |

## Invariants

- **IODA**: `Agent` orchestrates only; policy lives in Core, side effects in Tools/Providers.
- **Immutability**: context append methods return a new `AgentContext`, never mutate.
- **Stateless tools**: tools receive `ToolCall` only, never `AgentContext`.
- **Terminal tools**: `terminal=True` — loop exits on success; success from typed facts.
- **Typed outcomes**: protocol failures use `AgentResult.outcome`; no generic success fallback.
- **Metadata**: `Agent` injects `chat_id`, `user_id`, `profile_timezone` into every `ToolCall.metadata`.
- **Constraint prep**: `web_search`, `web_extract`, `schedule_task` dispatch through `ExecutionContextCore.prepare_tool_requests`.
- **Selection vs execution**: selection is tool-free; tools and profile preferences appear only in execution.

## Common tasks

### Adding a skill

1. Create `skills/specs/<name>.md` — YAML frontmatter (`name`, `description`,
   `tools`, optional `public`) + workflow + `tool_calls` examples.
2. No code changes. `catalog.py` auto-discovers specs at startup.

**Public vs private:** `public: true` (default) skills appear in chat
CAPABILITIES; `public: false` skills are selection-only (e.g. `manage_user_data`).
Selection always sees the full catalog.

### Adding a tool

1. Create `tools/<name>_tool.py` implementing `Tool` (`tool_port.py`) with a
   Pydantic `parameters_schema`.
2. Instantiate in `yoda_chat_bot.py` and inject into `Agent`.
3. Reference the tool name in skill specs that need it.
4. Set `terminal=True` if the tool alone completes the task.

### Infrastructure tools

- **`ask_user`** — suspends loop (execution only); Mind delivers the question.
- **`update_profile`** — persists profile fields via MemoryProvider; Agent
  canonicalizes preference writes before dispatch.

## Tests

```bash
.venv/bin/python -m pytest tests/test_react_loop.py tests/test_agent.py tests/test_mind_agent_pipeline.py -q
```

Routing evaluation: see [evaluation/AGENTS.md](../evaluation/AGENTS.md).

## Do not

- Put routing, validation, or constraint policy in `Agent` — use Core.
- Call one Operation from another; Integration passes data as parameters.
- Duplicate protocol prose here — update EPIC-002 / task `design.md` instead.
- Copy production transcripts into eval fixtures (ADR-000).
