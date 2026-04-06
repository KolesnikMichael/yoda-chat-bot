# Agent Module

Two-phase ReAct loop with declarative skills and typed tools. `AgentProvider` orchestrates; `ReactLoop` (Core) builds context and validates decisions.

## Two-phase execution

1. **Selection** — LLM sees a compact skill catalog (name + one-line description). Picks the best skill for the task.
2. **Execution** — Full skill spec + filtered tool schemas are injected. LLM follows the skill's workflow.

This keeps token usage low: the full catalog is small, and detailed specs load only for the selected skill.

### Message accumulation

Messages accumulate in `AgentContext.messages` across phases, giving the LLM continuity:

```
[system]    Executor role + JSON schema + user profile  (persisted in messages[0])
[user]      Task + skill catalog → "select a skill"
[assistant] {"selected_skill": "search_web", ...}
[user]      Skill activated + tool schemas → "now execute"
[assistant] {"tool_calls": [...], ...}
[system]    Tool results
[assistant] {"final_answer": "...", ...}
```

UTC time is appended as a trailing system message on each LLM call only — not stored in context.

## Suspend / resume

When `ask_user` fires, the loop suspends and `AgentContext` is saved to Redis via `AgentSessionProvider`. On `resume()`, context is restored. Session is deleted after final answer.

## Invariants

- **Immutability**: `append_assistant()` / `append_tool_results()` return a new `AgentContext`, never mutate.
- **Stateless tools**: tools receive only their `ToolCall`, never `AgentContext`.
- **Terminal tools**: `terminal=True` → loop exits immediately on success.
- **Nudge retry**: if LLM returns neither `tool_calls` nor `final_answer`, one retry with a nudge message.
- **Metadata injection**: `chat_id`, `user_id`, `profile_timezone` are added to every `ToolCall.metadata` by `AgentProvider`.

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
2. Instantiate in `yoda_chat_bot.py` and inject into `AgentProvider`.
3. Reference the tool name in skill specs that need it.
4. Set `terminal=True` if the tool completes the entire task by itself.

## Infrastructure tools (available to all skills)

- **`ask_user`** — suspends loop, signals clarification needed. Mind delivers the question in Yoda's voice.
- **`update_profile`** — saves user profile fields (timezone, location, etc.) via MemoryProvider. Can be batched with other tool calls.
