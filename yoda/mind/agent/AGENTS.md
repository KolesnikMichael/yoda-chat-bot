# Agent Module

Two-phase ReAct loop with declarative skills and typed tools. `AgentProvider` orchestrates; `ReactLoop` (Core) builds context and validates decisions.

## Two-phase execution

1. **Selection** — LLM receives a name-sorted discriminative skill catalog (`purpose`, `when_to_use`, `do_not_use_when`, `selection_examples`) as a `system` control message, plus the task and recent conversation as a separate `user` payload. Catalog order has no semantic priority.
2. **Execution** — Full skill workflow, required inputs, and filtered tool schemas are injected as a `system` activation message. The distilled task stays `user`. There is no synthetic assistant acknowledgement between task and activation.

This keeps token usage low: the selection catalog is compact, and detailed specs load only for the selected skill.

### Message accumulation

Messages accumulate in `AgentContext.messages` across phases, giving the LLM continuity:

```
[system]    Executor role + JSON schema + user profile  (persisted in messages[0])
[system]    <skill_selection_control> catalog + selection rules
[user]      <selection_input> recent conversation + task
[assistant] {"selected_skill": "search_web", ...}
--- Phase 2 rebuilds a compact transcript ---
[system]    Executor role + JSON schema + user profile
[user]      Distilled task
[system]    Skill activated + workflow + tool schemas
[assistant] {"tool_calls": [...], ...}
[system]    Tool results (and agent nudges)
[assistant] {"final_answer": "...", ...}
```

UTC time is appended as a trailing system message on each LLM call only — not stored in context.

Clarification answers from the user remain `user`. Agent-initiated execution nudges use `system`.

## Suspend / resume

When `ask_user` fires, the loop suspends and `AgentContext` is saved to Redis via `AgentSessionProvider`. On `resume()`, context is restored. Session is deleted after final answer.

If a resumed session is still in pre-selection (`active_skill is None`), `AgentProvider` refreshes the selection seed from the current validated catalog before the next selector call. Legacy combined catalog-in-user transcripts are rewritten into the control/input split while preserving the user-data prefix and later clarification messages.

## Invariants

- **Immutability**: `append_assistant()` / `append_tool_results()` return a new `AgentContext`, never mutate.
- **Stateless tools**: tools receive only their `ToolCall`, never `AgentContext`.
- **Terminal tools**: `terminal=True` → loop exits immediately on success.
- **Nudge retry**: if LLM returns neither `tool_calls` nor `final_answer`, one retry with a `system` nudge message.
- **Metadata injection**: `chat_id`, `user_id`, `profile_timezone` are added to every `ToolCall.metadata` by `AgentProvider`.

## Adding a new skill

1. Create `skills/specs/<name>.md` — YAML frontmatter with:
   - identity / public view: `name`, `description`, `public` (default `true`)
   - selection contract (required, validated at catalog load): `purpose`, `when_to_use`, `do_not_use_when`, `selection_examples`
   - execution: `tools`, `required_inputs`, `max_iterations`, plus workflow body and tool_calls examples
2. No code changes. `catalog.py` auto-discovers specs at startup and fails fast if selection metadata is missing or malformed.

### Public vs private skills

Skills have a `public` field in frontmatter (default: `true`).

- **Public** skills are advertised to users in the chat system prompt (== CAPABILITIES == block) via `description`. When a user asks "what can you do?", the chat LLM describes these naturally.
- **Private** skills (`public: false`) are hidden from the capabilities list but still available to the agent during skill selection. Use for internal/operational skills (e.g. `manage_user_data`).

The agent selection phase always sees the full catalog (public + private). Selection ignores `description`; the public capabilities view ignores selection-only fields.

## Adding a new tool

1. Create `tools/<name>_tool.py` implementing the `Tool` port (`tool_port.py`) with a Pydantic `parameters_schema`.
2. Instantiate in `yoda_chat_bot.py` and inject into `AgentProvider`.
3. Reference the tool name in skill specs that need it.
4. Set `terminal=True` if the tool completes the entire task by itself.

## Infrastructure tools (available to all skills)

- **`ask_user`** — suspends loop, signals clarification needed. Mind delivers the question in Yoda's voice.
- **`update_profile`** — saves user profile fields (timezone, location, etc.) via MemoryProvider. Can be batched with other tool calls.
