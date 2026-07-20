# Agent Module

Two-phase ReAct loop with declarative skills and typed tools. `Agent`
(Integration) orchestrates; `ReactLoop` (Core) builds phase-specific context and
validates decisions; Providers adapt language, sessions, and tools.

## Two-phase execution

1. **Selection** — tool-free. LLM sees a compact skill catalog (control message)
   and returns a `SelectionDecision`: `select_skill` (with distilled task) or
   `no_skill` (`reason=unsupported`). No tools, no clarification, no final answer.
2. **Execution** — after skill activation. Full skill spec + filtered tool schemas
   are injected. LLM returns an `ExecutionDecision`: `call_tools` or `finish`.

Phase-specific Pydantic models use `extra="forbid"`. Semantic cross-field and
membership rules live in `ReactLoop.validate_selection_decision` /
`validate_execution_decision` and return `ProtocolIssue`, never answer strings.

### Corrective retry

Each phase has one persisted boolean budget (`selection_retry_used` /
`execution_retry_used`). On malformed or invalid output, `ReactLoop.append_correction`
appends a closed-template `system` message and marks the budget used. A second
failure returns typed `AgentFailure(category="protocol_exhausted")` and deletes
any pending session. Rejected model output is never appended as accepted history.

### Message accumulation

Messages accumulate in `AgentContext.messages` across the active phase:

```
[system]    Selection or execution role + phase JSON schema + profile
[system]    Selection control catalog (selection only)
[user]      Selection input / task
[assistant] Phase decision JSON
[system]    Tool results (execution)
[assistant] {"mode":"finish","final_answer":"..."}
```

UTC time is appended as a trailing system message on each LLM call only — not
stored in context.

## Suspend / resume

When `ask_user` fires (execution only), the loop suspends and `AgentContext`
(including `phase`, retry flags, and `protocol_version`) is saved via
`AgentSessionProvider`. On `resume()`, context is restored. Sessions with
`protocol_version < 2` are upgraded lazily: pre-selection refreshes the catalog
seed; active execution replaces only the recognized generated base system
message. Historical combined-decision assistant JSON stays opaque. Session is
deleted after final answer or typed protocol failure.

If a resumed session is still in pre-selection (`active_skill is None`),
`Agent` refreshes the selection seed from the current validated catalog before
the next selector call. Legacy combined catalog-in-user transcripts are rewritten
into the control/input split while preserving the user-data prefix and later
clarification messages.

## Invariants

- **Immutability**: `append_assistant()` / `append_tool_results()` /
  `append_correction()` return a new `AgentContext`, never mutate.
- **Stateless tools**: tools receive only their `ToolCall`, never `AgentContext`.
- **Terminal tools**: `terminal=True` → loop exits immediately on success.
- **Typed failures**: unsupported / protocol / iteration exhaustion use
  `AgentResult.failure`; there is no `"Task completed."` fallback for those paths.
- **Metadata injection**: `chat_id`, `user_id`, `profile_timezone` are added to
  every `ToolCall.metadata` by `Agent`.

## Adding a new skill

1. Create `skills/specs/<name>.md` — YAML frontmatter (`name`, `description`, `tools`) + workflow instructions + tool_calls examples.
2. No code changes. `catalog.py` auto-discovers specs at startup.

### Public vs private skills

Skills have a `public` field in frontmatter (default: `true`).

- **Public** skills are advertised to users in the chat system prompt (== CAPABILITIES == block). When a user asks "what can you do?", the chat LLM describes these naturally.
- **Private** skills (`public: false`) are hidden from the capabilities list but still available to the agent during skill selection. Use for internal/operational skills (e.g. `manage_user_data`).

The agent selection phase always sees the full catalog (public + private).

## Adding a new tool

1. Create `tools/<name>_tool.py` implementing the `Tool` port (`tool_port.py`) with a Pydantic `parameters_schema`.
2. Instantiate in `yoda_chat_bot.py` and inject into `Agent`.
3. Reference the tool name in skill specs that need it.
4. Set `terminal=True` if the tool completes the entire task by itself.

## Infrastructure tools (available after skill activation)

- **`ask_user`** — suspends loop, signals clarification needed. Mind delivers the question in Yoda's voice. Not available during selection.
- **`update_profile`** — saves user profile fields (timezone, location, etc.) via MemoryProvider. Can be batched with other tool calls.
