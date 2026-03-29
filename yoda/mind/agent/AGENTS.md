# Agent Module Design

## Architecture: IODA Runtime + Declarative Skills + Typed Tools

IODA governs the runtime (pipelines, tool execution, state). Skills are declarative specifications loaded at runtime. Tools are typed async adapters. Multi-turn conversation preserves LLM reasoning across phases.

---

## Architectural Layers

```
Mind (IODA Integration)
  → AgentProvider (IODA Façade + Integration)
    → ReactLoop (IODA Core) — builds context, validates decisions
      → Skill Spec (declarative, loaded at runtime) — describes workflow for LLM
        → Tools (IODA Providers) — typed async adapters
```

Key principle: **IODA applies to the runtime, not to agent behavior.** The runtime (how skills are loaded, how tools are called, how state flows) follows IODA rules. The behavior (which skill to use, in what order) is the LLM's responsibility, guided by skill specifications.

---

## Internal Structure

```
agent/
  core/
    react_loop.py          # Core (sync): builds LLM context, validates Decision
  skills/
    catalog.py             # Core (sync): loads and indexes skill specs
    specs/
      schedule_message.md  # ✓ Implemented: one-time reminder scheduling
      manage_jobs.md       # ✓ Implemented: list/cancel scheduled jobs
      search_web.md        # ✓ Implemented: web search + extract via Tavily
  tools/
    tool_port.py           # Port: abstract Tool interface with terminal flag
    ask_user_tool.py       # ✓ Implemented: suspends loop for clarification
    scheduler_tool.py      # ✓ Implemented: schedules jobs via APScheduler (terminal)
    list_jobs_tool.py      # ✓ Implemented: lists active jobs from Redis
    cancel_job_tool.py     # ✓ Implemented: cancels jobs via APScheduler + Redis
    update_profile_tool.py # ✓ Implemented: saves user profile fields via MemoryProvider
    web_search_tool.py     # ✓ Implemented: Tavily search API adapter
    web_extract_tool.py    # ✓ Implemented: Tavily URL content extraction adapter
  session_provider.py      # Provider (async): persists/restores AgentContext via StorageApi
  agent_provider.py        # Integration (async): orchestrates multi-turn loop with suspend/resume
```

---

## Multi-turn Conversation Model

The agent accumulates a full conversation history (`AgentContext.messages`) across phases. The LLM sees its own prior responses, which provides continuity from skill selection through tool execution to final answer.

### Message flow

```
[system]    Static prompt: executor role, JSON schema, tool schemas, profile
[user]      "Task: ... \n Available skills: ... \n Select the best skill."
[assistant] {"selected_skill": "search_web", "reasoning": "..."}
[user]      "Skill 'search_web' activated. Workflow: ... Now execute."
[assistant] {"tool_calls": [{"tool_name": "web_search", ...}], "reasoning": "..."}
[system]    "[web_search] (OK) Found 5 results for ..."
[assistant] {"final_answer": "...", "reasoning": "sufficient data"}
```

- **System prompt** is static: executor role, JSON schema, all tool schemas, user profile. Built fresh each LLM call (UTC time updates).
- **Conversation messages** accumulate in `AgentContext.messages` and persist across iterations.
- **Tool results** are injected as `role: "system"` messages.
- **Assistant responses** (the LLM's structured JSON decisions) are preserved as `role: "assistant"` messages.

### Phase transition

Phase 1 (skill selection) → Phase 2 (execution) happens via conversation: the LLM's skill selection response is kept, then a `user` message activates the skill with its full spec and execution instruction.

---

## Skills Layer

A Skill is a **declarative specification** — not code. It describes:
- **When** to apply (trigger conditions, user intent patterns)
- **What inputs** are needed (may require clarification from user)
- **Which tools** to use and in what workflow
- **Examples** of tool_calls JSON for the LLM
- **Completion criteria** (when the skill is done)

### Skill catalog

`catalog.py` loads skill specs from `skills/specs/` at startup and builds a compact index (name + description) for the LLM. Full spec is loaded only when the LLM selects a skill.

### Two-phase token optimization

1. **Selection phase**: LLM sees only the compact catalog (~50-80 tokens per skill). Picks the best skill for the task.
2. **Execution phase**: full spec of the selected skill is loaded into context (~200-500 tokens). LLM follows the workflow using available tools.

---

## Tools Layer

Tools are **typed async adapters** — thin wrappers around external services with validated parameters. They serve as a **security boundary**: no matter what the LLM generates, it can only call predefined tools with typed inputs.

Each tool implements the `Tool` port (`tool_port.py`) with a Pydantic `parameters_schema` for auto-generated descriptions and input validation.

### Tool properties

- **`terminal: bool`** (default `False`) — when a terminal tool succeeds, the ReAct loop exits immediately. Used for tools that complete the task (e.g. `schedule_message`). Non-terminal tools (e.g. `update_profile`, `web_search`) can be called multiple times.

### Infrastructure tools

Available to all skills:

- **`ask_user`** — suspends the loop, signals clarification needed. Mind delivers the question through Yoda's voice.
- **`update_profile`** — saves user profile fields (timezone, location, etc.) via MemoryProvider. Can be batched with other tool calls.

### Tool rules

- No business logic in adapters.
- Pydantic schema on each tool auto-generates the tool catalog for the LLM.
- Tool metadata (`ToolCall.metadata`) carries runtime context (`chat_id`, `user_id`) injected by AgentProvider.

---

## Core: react_loop.py

Builds LLM context from static system prompt + accumulated messages. Validates the structured `Decision` (via JSON mode + Pydantic parsing). Manages iteration limits.

Key methods:
- `build_context()` — returns `[system_prompt] + context.messages`
- `build_selection_message()` — Phase 1 user message with task + catalog
- `build_activation_message()` — Phase 2 transition with skill spec + execution instruction
- `append_assistant()` — saves LLM Decision as assistant message
- `append_tool_results()` — adds tool results as system messages, increments iteration

---

## Façade + Integration: agent_provider.py

Orchestrates the multi-turn loop with suspend/resume support. No business logic.

### Robustness mechanisms

- **Nudge retry**: if the LLM returns neither `tool_calls` nor `final_answer`, a user message is appended ("You must call a tool or set final_answer") and the LLM gets one more attempt. The model sees its own empty response before the nudge.
- **Terminal tool auto-exit**: when a tool with `terminal=True` succeeds, the loop breaks immediately.
- **Tool metadata injection**: `chat_id`, `user_id`, `profile_timezone` are added to every `ToolCall.metadata` automatically.

---

## Security Model

Typed tools are the **security boundary**. Even if the LLM is manipulated via prompt injection:
- It can only call predefined tools with validated Pydantic parameters
- No `bash` or arbitrary code execution tool exists
- Each tool adapter validates its inputs before calling external services
- Skill specs are loaded from the project's filesystem (trusted source), not from user input

---

## Adding New Capabilities

### New skill
1. Create `skills/specs/<name>.md` with frontmatter + instructions + examples.
2. No code changes — catalog picks it up automatically at startup.

### New tool
1. Create `tools/<name>_tool.py` implementing `Tool` with a Pydantic params schema.
2. In `yoda_chat_bot.py`, instantiate and inject into `AgentProvider`.
3. Reference the tool name in skill specs that need it.

---

## Dual LLM Roles: Yoda vs Executor

| | **Yoda (conversational)** | **Executor (agentic)** |
|---|---|---|
| System prompt | Personality, style, emotions | Neutral, instrumental |
| Context | Conversation (full chat history) | AgentContext (multi-turn messages) |
| Output | Reply to user in Yoda's voice | Structured AgentResult |
| Calls tools | No | Yes |
| Knows about skills | No | Yes |

The two LLMs don't know about each other. They communicate via Conversation (Data), mediated by Mind (Integration).

### Intent classification

Mind classifies intent via LLM with awareness of pending agent sessions:
- `"chat"` — Yoda answers directly
- `"agent_task"` — full delegation to Executor via `AgentProvider.run()`
- `"agent_resume"` — pending session exists, user's message is an answer → `AgentProvider.resume()`
- `"augmented_chat"` — (planned) Yoda needs quick context from a single tool, no full ReAct cycle

---

## Agent Session Runtime

### Isolated sessions

Each `AgentProvider.run()` creates its own `AgentContext`. Guarantees:
- **No cross-user contamination**: parallel calls for different chats get independent contexts
- **Immutability per step**: `append_assistant()` / `append_tool_results()` return new AgentContext, never mutate
- **Stateless tools**: tools receive only their `ToolCall`, never a reference to AgentContext

### Persistence via `AgentSessionProvider`

- **Clarification flow** — when `ask_user` suspends the loop, `AgentProvider` saves AgentContext (including full messages) to Redis. On `resume()`, context is restored and the conversation continues.
- **Session cleanup** — after final answer, session is deleted.

### Memory scope hierarchy

| Scope | Lifetime | Stores | Location |
|---|---|---|---|
| **Tool** | Single `execute()` call | Nothing (stateless) | — |
| **Skill execution** | One ReAct cycle | Messages, iteration state | AgentContext |
| **Conversation** | Entire chat | Messages, injected agent results | Conversation + MemoryProvider |
| **User profile** | Permanent | Facts, preferences, timezone | UserProfile + StorageApi |
| **Active jobs** | Until delivered or cancelled | Job metadata | `active_jobs:<chat_id>` in Redis |
