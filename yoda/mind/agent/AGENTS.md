# Agent Module Design

## Architecture: IODA Runtime + Declarative Skills + Typed Tools

IODA governs the runtime (pipelines, tool execution, state). Skills are declarative specifications loaded at runtime. Tools are typed async adapters in code. Two-phase token optimization: compact skill catalog on every turn, full spec only for the selected skill.

---

## Architectural Layers

```
Mind (IODA Integration)
  → AgentProvider (IODA Façade + Integration)
    → ReactLoop (IODA Core) — picks a skill from the catalog
      → Skill Spec (declarative, loaded at runtime) — describes workflow for LLM
        → Tools (IODA Providers) — typed async adapters
```

Key principle: **IODA applies to the runtime, not to agent behavior.** The runtime (how skills are loaded, how tools are called, how state flows) follows IODA rules. The behavior (which skill to use, in what order) is the LLM's responsibility, guided by skill specifications.

---

## Internal Structure

Current implementation + planned extensions:

```
agent/
  core/
    react_loop.py          # Core (sync): builds LLM context, validates Decision
  skills/
    catalog.py             # Core (sync): loads and indexes skill specs
    specs/
      schedule_message.md  # ✓ Implemented: one-time reminder scheduling
      deep_research.md     # Planned: multi-step web research
      quick_lookup.md      # Planned: simple search → answer
      memory_recall.md     # Planned: query conversation history
  tools/
    tool_port.py           # Port: abstract Tool interface with terminal flag
    ask_user_tool.py       # ✓ Implemented: suspends loop for clarification
    scheduler_tool.py      # ✓ Implemented: schedules jobs via APScheduler (terminal)
    update_profile_tool.py # ✓ Implemented: saves user profile fields via MemoryProvider
    web_search_tool.py     # Planned: search API adapter
    browser_tool.py        # Planned: page scraping adapter
    memory_tool.py         # Planned: conversation memory adapter
  session_provider.py      # Provider (async): persists/restores AgentContext via StorageApi
  agent_provider.py        # Integration (async): orchestrates two-phase loop with suspend/resume
```

---

## Skills Layer

A Skill is a **declarative specification** — not code. It describes:
- **When** to apply (trigger conditions, user intent patterns)
- **What inputs** are needed (may require clarification from user)
- **Which tools** to use and in what workflow
- **Completion criteria** (when the skill is done)

### Skill's instructions example

```markdown
# Search Web

## When to use
- User directly or implicitly asks you to provide information about a topic
- You need to back up your next statement with up-to-date facts

## Workflow
1. Search for the topic using `web_search`.
2. If results are insufficient, extract content from one or more most relevant URLs with `web_extract`.
3. Synthesize findings into a coherent answer.
4. If gaps remain and iterations allow, search for specific sub-topics.

## Completion
Stop when: enough data for a comprehensive answer, OR max iterations reached.
```

### Skill catalog

`catalog.py` loads skill specs from `skills/specs/` at startup and builds a compact index (name + description) for the LLM. Full spec is loaded only when the LLM selects a skill.

### Two-phase token optimization

1. **Selection phase**: LLM sees only the compact catalog (~50-80 tokens per skill). Picks the best skill for the task.
2. **Execution phase**: full spec of the selected skill is loaded into context (~200-500 tokens). LLM follows the workflow using available tools.

This avoids paying for all skill instructions on every turn.

---

## Tools Layer

Tools are **typed async adapters** — thin wrappers around external services with validated parameters. They serve as a **security boundary**: no matter what the LLM generates, it can only call predefined tools with typed inputs.

Each tool implements the `Tool` port (`tool_port.py`) with a Pydantic `parameters_schema` for auto-generated descriptions and input validation.

### Tool properties

- **`terminal: bool`** (default `False`) — when a terminal tool succeeds, the ReAct loop exits immediately. Used for tools that complete the task (e.g. `schedule_message`). Non-terminal tools (e.g. `update_profile`, `web_search`) can be called multiple times with different arguments.

### Infrastructure tools

These tools are available to all skills and handle cross-cutting concerns:

**`ask_user`** — control flow tool. For the LLM it looks like a regular tool; internally it returns a ToolResult with `suspend=True`, signalling the loop to save context and wait for user input. The actual message delivery is Mind's responsibility (through Yoda LLM, so the question is rephrased in character). This preserves full isolation: Executor doesn't know about Telegram or Yoda.

**`update_profile`** — saves user profile fields (timezone, location, etc.) via MemoryProvider. Skills that learn new information about the user (e.g. via `ask_user`) should call `update_profile` alongside the main tool in the same `tool_calls` batch. Validates fields against a whitelist. Requires `user_id` and `chat_id` in tool metadata.

### Tool rules

- No business logic in adapters.
- If result needs transformation, add a sync Core function and call it here.
- Adapters may use Providers (e.g. `LanguageProvider` for summarisation).
- Pydantic schema on each tool auto-generates the tool catalog for the LLM.
- Tool metadata (`ToolCall.metadata`) carries runtime context (`chat_id`, `user_id`) that the LLM doesn't control.

---

## Core: react_loop.py

Builds LLM context, validates the Decision, manages iteration limits. The LLM produces a structured `Decision` (via JSON mode + Pydantic parsing). ReactLoop validates it but doesn't contain reasoning logic — that's the LLM's job, guided by the skill spec.

All tool observations (results) are injected as `role: "user"` messages — required by Mistral API (last message must be user role). The execution instruction includes concrete JSON examples for tool calls to guide the LLM's structured output.

---

## Façade + Integration: agent_provider.py

Orchestrates the two-phase loop with suspend/resume support. No business logic.

### Robustness mechanisms

- **Nudge retry**: if the LLM returns neither `tool_calls` nor `final_answer` (describes intent in `reasoning` but doesn't act), a system observation is injected ("You must call a tool or set final_answer") and the LLM gets one more attempt.
- **Terminal tool auto-exit**: when a tool with `terminal=True` succeeds, the loop breaks immediately — prevents the LLM from re-calling the same tool.
- **Tool metadata injection**: `chat_id` and `user_id` are added to every `ToolCall.metadata` automatically, so tools can access runtime context without the LLM needing to provide it.

---

## Security Model

Typed tools are the **security boundary**. Even if the LLM is manipulated via prompt injection:
- It can only call predefined tools with validated Pydantic parameters
- No `bash` or arbitrary code execution tool exists
- Each tool adapter validates its inputs before calling external services
- Skill specs are loaded from the project's filesystem (trusted source), not from user input or community registries

### Threat mitigations

| Threat | Mitigation |
|---|---|
| Prompt injection via user message | LLM sees user text in a separate role; system prompt + skill spec have higher priority |
| Malicious skill spec | Skills loaded only from project filesystem, not user-contributed |
| Tool parameter manipulation | Pydantic validation on every tool call; invalid params → ToolResult(success=False) |
| Data exfiltration via tools | No generic HTTP tool; each tool has a narrow, specific purpose |

---

## Adding New Capabilities

### New skill (e.g. "monitor website")
1. Create `skills/specs/monitor_website.md` with frontmatter + instructions.
2. No code changes — catalog picks it up automatically at startup.

### New tool (e.g. "web search")
1. Create `tools/web_search_tool.py` implementing `Tool` with a Pydantic params schema.
2. In `yoda_chat_bot.py`, instantiate and inject into `AgentProvider`.
3. Reference the tool name in skill specs that need it.

### New skill + new tool
1. Create the tool adapter first (code).
2. Create the skill spec referencing it (markdown).
3. Wire the tool in `yoda_chat_bot.py`.

---

## Anti-patterns

| Anti-pattern | Fix |
|---|---|
| Business logic in `agent_provider.py` | Move to `react_loop.py` (validation) or skill spec (workflow) |
| Tool adapter with free-text parameters | Use Pydantic model with constrained fields |
| Skill spec referencing non-existent tool | `catalog.py` validates tool references at load time |
| All skill specs loaded into every LLM call | Two-phase: catalog first, full spec only for selected skill |
| Hardcoded workflow in Python instead of skill spec | If the workflow is LLM-driven, it belongs in a skill spec |

---

## Dual LLM Roles: Yoda vs Executor

The system uses two separate LLM roles with distinct responsibilities:

| | **Yoda (conversational)** | **Executor (agentic)** |
|---|---|---|
| System prompt | Personality, style, emotions | Neutral, instrumental |
| Context | Conversation (full chat history) | AgentContext (task + tool results) |
| Output | Reply to user in Yoda's voice | Structured AgentResult |
| Calls tools | No | Yes |
| Knows about skills | No | Yes |

The two LLMs don't know about each other. They communicate via Conversation (Data), mediated by Mind (Integration). Yoda LLM receives agent output as a system message in Conversation. It doesn't know an agent produced it — it just sees contextual information and responds in character. For clarifications, Yoda rephrases the Executor's question in its own voice.

Benefits:
- **Token efficiency**: Executor doesn't pay for Yoda's personality prompt. Yoda doesn't pay for tool schemas / skill specs.
- **Separation of concerns**: Executor focuses on task execution. Yoda focuses on natural conversation.
- **Testability**: each role tested independently — mock tools for Executor, mock conversation for Yoda.

### Intent classification

Mind classifies intent via LLM with awareness of pending agent sessions:
- `"chat"` — Yoda answers directly
- `"agent_task"` — full delegation to Executor via `AgentProvider.run()`
- `"agent_resume"` — pending session exists for this chat, user's message is an answer to Executor's question → `AgentProvider.resume()` (shortcut: no LLM call needed)
- `"augmented_chat"` — (planned) Yoda needs context (quick single-tool lookup, no full ReAct cycle). Mind calls a tool directly, injects result, Yoda responds.

---

## Agent Session Runtime

### Isolated sessions

Each `AgentProvider.run()` creates its own `AgentContext`. Guarantees:
- **No cross-user contamination**: parallel calls for different chats get independent contexts
- **Immutability per iteration**: `observe()` returns a new AgentContext, never mutates
- **Stateless tools**: tools receive only their `ToolCall`, never a reference to AgentContext

### Context management

AgentContext.history grows with each iteration. Three mechanisms to control it:

**Token budget** (planned): `ReactLoop.build_context()` respects model's context limit. When history exceeds budget:
- Summarize older ToolResults (one short LLM call)
- Or sliding window: keep first + last N results, drop middle

**Persistence** via `AgentSessionProvider` (async, uses StorageApi):
- **Clarification flow** — when `ask_user` tool suspends the loop, `AgentProvider` saves AgentContext (including `user_id`) to Redis via `AgentSessionProvider.save()`. On `resume()`, context is loaded via `AgentSessionProvider.load()`. After final answer, session is deleted.
- **Cron / monitoring** (planned) — periodic tasks. Each run creates a new AgentContext, but may reference previous results stored in long-term memory.
- **Session timeout** (planned) — pending sessions expire after a configurable TTL (e.g. 30 minutes). CognitionCore checks session existence before classifying intent as `"agent_resume"`.

**Timeout / cancellation** (planned): protection against hung LLM calls or tools:
- `AgentProvider.run()` has overall timeout
- Each tool call wrapped in `asyncio.wait_for()`
- On timeout → `AgentResult(error="timeout")` → Mind decides what to tell the user

### Memory scope hierarchy

| Scope | Lifetime | Stores | Location |
|---|---|---|---|
| **Tool** | Single `execute()` call | Nothing (stateless) | — |
| **Skill execution** | One ReAct cycle | Tool results, iteration state | AgentContext |
| **Conversation** | Entire chat | Messages, injected agent results | Conversation + MemoryProvider |
| **User profile** | Permanent | Facts, preferences, timezone | UserProfile + StorageApi |
| **Active jobs** | Until delivered (once) or cancelled (recurring) | Job metadata (type, description, timezone) | `active_jobs:<chat_id>` in Redis |

AgentContext (skill scope) is created and destroyed inside `AgentProvider.run()`. Its result is projected into Conversation (conversation scope) via Mind.

### Scheduled job lifecycle

Jobs are stored in two places: APScheduler's Redis job store (execution) and `active_jobs:<chat_id>` (metadata for listing/management).

1. **Created** by `scheduler_tool.py` → `SchedulerApi.schedule_once()` + metadata saved to `active_jobs:<chat_id>`
2. **Fired** by APScheduler → module-level `_fire_job()` (async, picklable) → delivery callback → Mind
3. **Cleaned up**: for `type=once`, metadata is auto-deleted from `active_jobs` after delivery. For `type=recurring` (planned), metadata persists until explicit cancellation.

---

## References

- SGR Agent Core (vamplabAI/sgr-agent-core) — structured output for Decision, Pydantic tool schemas
- OpenClaw (openclaw/openclaw) — skill catalog/discovery model, two-level skill/tool separation
- Discussion: agent_systems_skills_and_environment_engineering.md — CFS/RFS framing, skill ecosystem concepts
