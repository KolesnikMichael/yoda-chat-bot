
# Agent Module (mind/agent/) design draft

## Role in the System
From the IODA top-level perspective, the entire `agent/` directory is a single **async Provider** (`AgentProvider`). Its internal complexity is hidden behind one façade method:

```python
agent_result = await AgentProvider.run(task, profile)
```

Internally, `agent/` uses **Hexagonal Architecture** to isolate the ReAct reasoning loop from concrete tool implementations.

---

## Internal Structure

```
agent/
  core/
    react_loop.py      # Hexagonal CORE: pure sync reasoning, no tool knowledge
  ports/
    tool_port.py       # PORT: abstract Tool interface
  adapters/
    web_search_tool.py # ADAPTER: async, implements Tool
    browser_tool.py    # ADAPTER: async, implements Tool
    memory_tool.py     # ADAPTER: async, implements Tool
  agent_provider.py    # IODA FAÇADE + Integration: wires core + adapters, async
```

---

## Core: react_loop.py

**Sync. No imports from adapters. No async.**

Responsibilities:
- Given a `context: AgentContext`, decide: call a tool or produce a final answer.
- Update context after observing tool results.
- Determine when the loop is done.

```python
# Canonical shape
class ReactLoop:
    def decide(self, context: AgentContext) -> Decision:
        # pure logic: returns Decision(tool_calls=[...]) or Decision(final_answer="...")
        ...

    def observe(self, context: AgentContext, results: list[ToolResult]) -> AgentContext:
        # pure logic: integrates tool results into context
        ...

    def is_done(self, context: AgentContext) -> bool:
        # pure logic
        ...
```

Unit-testable with plain `AgentContext` objects, zero mocks.

---

## Port: tool_port.py

```python
from abc import ABC, abstractmethod
from mind.data.agent_result import ToolCall, ToolResult

class Tool(ABC):
    name: str

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        ...
```

All adapters implement this interface. `react_loop.py` never imports from `adapters/`.

---

## Adapters

Each adapter is **async**, thin, and focused on one external service:

```python
class WebSearchTool(Tool):
    name = "web_search"

    async def execute(self, call: ToolCall) -> ToolResult:
        # call external search API, return ToolResult
        ...
```

Rules:
- No business logic in adapters.
- If result needs transformation (e.g. parsing HTML → text), add a sync Core function and call it here.
- Adapters may use Providers (e.g. `LLMProvider` for summarisation) — that's fine.

---

## Façade + Integration: agent_provider.py

This is both the **IODA façade** (hides internal complexity) and the **Integration** (orchestrates the ReAct loop without logic).

```python
class AgentProvider:
    def __init__(self, react_loop: ReactLoop, tools: list[Tool]):
        self.loop  = react_loop
        self.tools = {t.name: t for t in tools}

    async def run(self, task: str, profile: UserProfile) -> AgentResult:
        context = AgentContext(task=task, profile=profile, history=[])

        while not self.loop.is_done(context):
            decision = self.loop.decide(context)          # sync

            if decision.final_answer:
                break

            # parallel tool execution
            results = await asyncio.gather(*[
                self.tools[call.tool_name].execute(call)
                for call in decision.tool_calls
            ])

            context = self.loop.observe(context, list(results))  # sync

        return AgentResult(
            answer=decision.final_answer,
            tools_used=[r.tool_name for r in context.history]
        )
```

Rules:
- `agent_provider.py` contains **no reasoning logic** — that lives in `react_loop.py`.
- `agent_provider.py` contains **no tool-specific logic** — that lives in adapters.
- Adding a new tool: instantiate its adapter and pass to constructor in `chat_bot.py`.

---

## Data Structures (in mind/data/)

```python
# agent_result.py
@dataclass
class ToolCall:
    tool_name: str
    arguments: dict

@dataclass
class ToolResult:
    tool_name: str
    output: str
    success: bool

@dataclass
class AgentContext:
    task: str
    profile: UserProfile
    history: list[ToolResult]

@dataclass
class AgentResult:
    answer: str
    tools_used: list[str]
```

---

## Testing Strategy

| Component | Test type | Mocks needed |
|---|---|---|
| `react_loop.py` | Unit | None — feed plain `AgentContext` objects |
| `adapters/*.py` | Unit/Integration | Mock external HTTP calls only |
| `agent_provider.py` | Acceptance | Mock `Tool.execute()` to return fixed `ToolResult` |

---

## Adding a New Tool

1. Create `adapters/my_tool.py` implementing `Tool`.
2. In `chat_bot.py` (Construction), instantiate and inject into `AgentProvider`.
3. Nothing else changes — `react_loop.py` discovers available tools from context/config.

---

## Anti-patterns

| Anti-pattern | Fix |
|---|---|
| `react_loop.py` importing any adapter | Use `Tool` port only |
| Logic in `agent_provider.py` (e.g. filtering results) | Move to `react_loop.observe()` |
| Sync tool execution (sequential) | Use `asyncio.gather()` for parallel calls |
| Tool adapter holding state between calls | Tools must be stateless; state lives in `AgentContext` |

---

## Ideas from SGR Agent Core (vamplabAI/sgr-agent-core)

Reviewed the SGR framework for reuse — it doesn't fit as a dependency (full standalone framework, deeply OpenAI-coupled, template-method inheritance instead of hexagonal). But three ideas are worth adapting:

### 1. Structured output for Decision

SGR's `ReasoningTool` is a Pydantic schema that the LLM fills via structured output — reasoning steps, situation assessment, plan status, and selected tool all come back as typed fields rather than free-text that needs parsing.

**Adaptation for Yoda:** `ReactLoop.decide()` could internally use LLM structured output to produce the `Decision` object. The Pydantic schema acts as a contract between the LLM and the loop, eliminating brittle text parsing. The `Decision` dataclass could carry optional reasoning metadata (steps taken, confidence) useful for logging and debugging, while the core flow (`tool_calls` / `final_answer`) stays unchanged.

### 2. Pydantic-based tool schemas (self-describing tools)

In SGR, each tool IS a Pydantic model — the model fields are the tool's parameters, and the schema auto-generates the tool description sent to the LLM. No hand-written tool descriptions to keep in sync.

**Adaptation for Yoda:** Each `Tool` adapter could expose a Pydantic model describing its parameters. `AgentProvider` would collect these schemas at construction time and pass them to `ReactLoop` as part of context, so the LLM always gets an accurate, auto-generated tool catalog. The `Tool` port interface stays abstract — the schema is an additional property, not a replacement.

### 3. Clarification mechanism (pause-and-ask)

SGR agents can pause mid-loop to ask the user for clarification before continuing research. The loop enters a `WAITING_FOR_CLARIFICATION` state and resumes when the user responds.

**Adaptation for Yoda:** `Decision` could include a `clarification_needed: str | None` field. When set, `AgentProvider.run()` would yield the question back to the caller (the Mind pipeline), which routes it through embodiment to the user. On the next message, the pipeline resumes the agent with the user's answer injected into context. This keeps the clarification flow inside the existing IODA pipeline model — no async events or internal state machines needed.