
# Agent Module — Design Draft

## Design Decision: Hybrid Architecture

Three approaches were considered for the agent module (see Appendix A for full comparison):

| Approach | Description | Token cost | Security | Fit for Yoda |
|---|---|---|---|---|
| **A. Skills as Code** | Skills are Python classes, IODA/Hexagonal throughout | Lowest | Best (typed tools = security boundary) | Good control, but rigid |
| **B. Skills as Prompts** (OpenClaw model) | Skills are SKILL.md files injected into system prompt, tools = bash | Highest (~4k-16k tokens/turn overhead) | Worst (skill = injection vector, bash = arbitrary exec) | Poor fit for multi-user Telegram bot |
| **C. Hybrid** (chosen) | IODA runtime + declarative skill specs + typed tool adapters | Low (two-phase: compact catalog + selected skill only) | Good (typed tools as security boundary, no arbitrary exec) | Best balance |

**Chosen: Hybrid (C).** IODA governs the runtime (pipelines, tool execution, state). Skills are declarative specifications loaded at runtime. Tools are typed async adapters in code.

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

```
agent/
  core/
    react_loop.py        # Core (sync): builds LLM context, validates Decision
  skills/
    catalog.py           # Core (sync): loads and indexes skill specs
    specs/
      deep_research.md   # Skill spec: when to use, required inputs, workflow, tools
      quick_lookup.md    # Skill spec: simple search → answer
      memory_recall.md   # Skill spec: query conversation history
  tools/
    tool_port.py         # Port: abstract Tool interface
    web_search_tool.py   # Provider (async): search API adapter
    browser_tool.py      # Provider (async): page scraping adapter
    memory_tool.py       # Provider (async): conversation memory adapter
  agent_provider.py      # Integration (async): orchestrates the two-phase loop
```

---

## Skills Layer

A Skill is a **declarative specification** — not code. It describes:
- **When** to apply (trigger conditions, user intent patterns)
- **What inputs** are needed (may require clarification from user)
- **Which tools** to use and in what workflow
- **Completion criteria** (when the skill is done)

### Skill spec format (example)

```markdown
---
name: deep_research
description: Research a topic using multiple searches, scraping, and synthesis.
required_inputs:
  - topic: "The subject to research"
tools:
  - web_search
  - browser_scrape
max_iterations: 5
---
# Deep Research

## When to use
User asks to investigate, research, or find detailed information about a topic.

## Workflow
1. Search for the topic using `web_search`.
2. If results are insufficient, scrape top URLs with `browser_scrape`.
3. Synthesize findings into a coherent answer.
4. If gaps remain and iterations allow, search for specific sub-topics.

## Completion
Stop when: enough data for a comprehensive answer, OR max iterations reached.
```

### Skill catalog

`catalog.py` loads skill specs from `skills/specs/` at startup and builds a compact index (name + description) for the LLM. Full spec is loaded only when the LLM selects a skill.

```python
class SkillCatalog:
    @staticmethod
    def load_catalog(skills_dir: Path) -> list[SkillSummary]:
        # parse frontmatter from each .md file, return name + description
        ...

    @staticmethod
    def load_skill(skills_dir: Path, skill_name: str) -> SkillSpec:
        # load full spec for the selected skill
        ...
```

### Two-phase token optimization

1. **Selection phase**: LLM sees only the compact catalog (~50-80 tokens per skill). Picks the best skill for the task.
2. **Execution phase**: full spec of the selected skill is loaded into context (~200-500 tokens). LLM follows the workflow using available tools.

This avoids paying for all skill instructions on every turn (the main cost problem with the OpenClaw approach).

---

## Tools Layer

Tools are **typed async adapters** — thin wrappers around external services with validated parameters. They serve as a **security boundary**: no matter what the LLM generates, it can only call predefined tools with typed inputs.

### Port: tool_port.py

```python
from abc import ABC, abstractmethod

class Tool(ABC):
    name: str
    parameters_schema: type[BaseModel]  # Pydantic model for auto-generated tool description

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        ...
```

### Tool adapters

Each adapter is async, stateless, and focused on one external service:

```python
class WebSearchParams(BaseModel):
    query: str
    max_results: int = 5

class WebSearchTool(Tool):
    name = "web_search"
    parameters_schema = WebSearchParams

    async def execute(self, call: ToolCall) -> ToolResult:
        params = WebSearchParams(**call.arguments)  # validates input
        # call external search API
        ...
```

Rules:
- No business logic in adapters.
- If result needs transformation, add a sync Core function and call it here.
- Adapters may use Providers (e.g. `LanguageProvider` for summarisation).
- Pydantic schema on each tool auto-generates the tool catalog for the LLM.

---

## Core: react_loop.py

Builds LLM context, validates the Decision, manages iteration limits.

```python
class ReactLoop:
    def build_context(self, agent_context: AgentContext) -> list[dict]:
        # builds LLM messages: system prompt + skill catalog or active skill spec + tool schemas + history
        ...

    def validate_decision(self, decision: Decision, agent_context: AgentContext) -> Decision:
        # checks: skill exists, tools exist, iteration limit, etc.
        ...

    def observe(self, context: AgentContext, results: list[ToolResult]) -> AgentContext:
        # integrates tool results into context
        ...

    def is_done(self, context: AgentContext) -> bool:
        ...
```

The LLM produces a structured `Decision` (via Pydantic structured output). ReactLoop validates it but doesn't contain reasoning logic — that's the LLM's job, guided by the skill spec.

---

## Façade + Integration: agent_provider.py

Orchestrates the two-phase loop. No business logic.

```python
class AgentProvider:
    def __init__(self, react_loop: ReactLoop, tools: list[Tool],
                 skill_catalog: SkillCatalog, language_provider: LanguageProvider):
        self.loop = react_loop
        self.tools = {t.name: t for t in tools}
        self.catalog = skill_catalog
        self.llm = language_provider

    async def run(self, task: str, profile: UserProfile) -> AgentResult:
        context = AgentContext(task=task, profile=profile, catalog=self.catalog)

        # Phase 1: skill selection
        messages = self.loop.build_context(context)        # includes compact catalog
        raw_decision = await self.llm.structured_output(messages, Decision)
        decision = self.loop.validate_decision(raw_decision, context)

        if decision.selected_skill:
            context = context.with_active_skill(
                self.catalog.load_skill(decision.selected_skill))

        # Phase 2: iterative execution
        while not self.loop.is_done(context):
            messages = self.loop.build_context(context)    # includes active skill spec + tool schemas
            raw_decision = await self.llm.structured_output(messages, Decision)
            decision = self.loop.validate_decision(raw_decision, context)

            if decision.final_answer:
                break

            if decision.clarification_needed:
                return AgentResult(clarification=decision.clarification_needed)

            results = await asyncio.gather(*[
                self.tools[call.tool_name].execute(call)
                for call in decision.tool_calls
            ])

            context = self.loop.observe(context, list(results))

        return AgentResult(answer=decision.final_answer,
                           tools_used=context.tools_used)
```

---

## Data Structures (in mind/data/)

```python
@dataclass
class SkillSummary:
    name: str
    description: str

@dataclass
class SkillSpec:
    name: str
    description: str
    required_inputs: dict[str, str]
    tools: list[str]
    instructions: str              # full markdown body
    max_iterations: int = 10

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
class Decision:
    selected_skill: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_answer: str | None = None
    clarification_needed: str | None = None
    reasoning: str = ""            # for logging/debugging

@dataclass
class AgentContext:
    task: str
    profile: UserProfile
    catalog: SkillCatalog
    active_skill: SkillSpec | None = None
    history: list[ToolResult] = field(default_factory=list)
    iteration: int = 0
    tools_used: list[str] = field(default_factory=list)

@dataclass
class AgentResult:
    answer: str | None = None
    clarification: str | None = None
    tools_used: list[str] = field(default_factory=list)
```

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

## Testing Strategy

| Component | Test type | Mocks needed |
|---|---|---|
| `react_loop.py` | Unit | None — feed plain `AgentContext` objects |
| `catalog.py` | Unit | None — load from test fixture .md files |
| `tools/*.py` | Unit/Integration | Mock external HTTP calls only |
| `agent_provider.py` | Acceptance | Mock `Tool.execute()` + `LanguageProvider.structured_output()` |

---

## Adding New Capabilities

### New skill (e.g. "monitor website")
1. Create `skills/specs/monitor_website.md` with frontmatter + instructions.
2. No code changes — catalog picks it up automatically at startup.

### New tool (e.g. "cron scheduler")
1. Create `tools/cron_tool.py` implementing `Tool` with a Pydantic params schema.
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

## Appendix A: Approach Comparison

### A. Skills as Code
- Skills are Python classes following IODA patterns
- Token cost: lowest (~300-500 tokens for tool schemas)
- Security: best (typed tools, no injection vector through skills)
- Flexibility: lowest (new skill = new code + deploy)

### B. Skills as Prompt Instructions (OpenClaw model)
- Skills are SKILL.md files fully injected into system prompt; tools = bash
- Token cost: highest (~4k-16k tokens overhead per turn for all skill instructions)
- Security: worst (skill IS a prompt injection vector; bash = arbitrary code execution)
- Flexibility: highest (change markdown, no deploy)
- Poor fit for multi-user Telegram bot (security + cost)

### C. Hybrid (chosen for Yoda)
- IODA runtime + declarative skill specs + typed tool adapters
- Token cost: low (compact catalog + selected skill only, ~600-1500 tokens)
- Security: good (typed tools as boundary; no bash; skills from trusted source)
- Flexibility: good (new skill = new .md file; new tool = new adapter + wire)

Key references:
- SGR Agent Core (vamplabAI/sgr-agent-core) — structured output for Decision, Pydantic tool schemas
- OpenClaw (openclaw/openclaw) — skill catalog/discovery model, two-level skill/tool separation
- Discussion: agent_systems_skills_and_environment_engineering.md — CFS/RFS framing, skill ecosystem concepts