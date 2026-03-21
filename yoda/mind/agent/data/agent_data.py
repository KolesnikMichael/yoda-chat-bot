from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from yoda.mind.memory.data.user_profile import UserProfile


# --- Skill data ---

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
    instructions: str
    max_iterations: int = 10


# --- Tool call / result ---

@dataclass
class ToolCall:
    tool_name: str
    arguments: dict
    metadata: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    tool_name: str
    output: str
    success: bool
    suspend: bool = False


# --- LLM Decision (Pydantic for structured output) ---

class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict


class Decision(BaseModel):
    selected_skill: str | None = None
    tool_calls: list[ToolCallRequest] | None = Field(default=None)
    final_answer: str | None = None
    reasoning: str = ""

    @property
    def effective_tool_calls(self) -> list[ToolCallRequest]:
        return self.tool_calls or []


# --- Agent context / result ---

@dataclass
class AgentContext:
    task: str
    profile: UserProfile
    chat_id: int
    user_id: int = 0
    catalog_summaries: list[SkillSummary] = field(default_factory=list)
    active_skill: SkillSpec | None = None
    history: list[ToolResult] = field(default_factory=list)
    iteration: int = 0
    tools_used: list[str] = field(default_factory=list)

    def with_active_skill(self, skill: SkillSpec) -> AgentContext:
        return AgentContext(
            task=self.task,
            profile=self.profile,
            chat_id=self.chat_id,
            user_id=self.user_id,
            catalog_summaries=self.catalog_summaries,
            active_skill=skill,
            history=self.history,
            iteration=self.iteration,
            tools_used=self.tools_used,
        )


@dataclass
class AgentResult:
    answer: str | None = None
    clarification: str | None = None
    tools_used: list[str] = field(default_factory=list)
