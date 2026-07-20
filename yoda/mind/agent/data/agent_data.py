from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from yoda.mind.memory.data.user_profile import UserProfile


# --- Skill data ---

@dataclass
class SkillSummary:
    name: str
    description: str
    public: bool = True
    purpose: str = ""
    when_to_use: list[str] = field(default_factory=list)
    do_not_use_when: list[str] = field(default_factory=list)
    selection_examples: list[str] = field(default_factory=list)


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


# --- Phase protocol (Pydantic for structured output) ---

class AgentPhase(StrEnum):
    SELECTION = "selection"
    EXECUTION = "execution"


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    arguments: dict


class SelectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["select_skill", "no_skill"]
    selected_skill: str | None = None
    distilled_task: str | None = None
    reason: Literal["unsupported"] | None = None
    reasoning: str = ""


class ExecutionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["call_tools", "finish"]
    tool_calls: list[ToolCallRequest] | None = None
    final_answer: str | None = None
    reasoning: str = ""


class ProtocolIssueCategory(StrEnum):
    MALFORMED_OUTPUT = "malformed_output"
    INVALID_MODE = "invalid_mode"
    UNKNOWN_SKILL = "unknown_skill"
    UNKNOWN_TOOL = "unknown_tool"
    ITERATION_LIMIT = "iteration_limit"


@dataclass(frozen=True)
class ProtocolIssue:
    stage: AgentPhase
    category: ProtocolIssueCategory


@dataclass(frozen=True)
class AgentFailure:
    stage: AgentPhase
    category: Literal["unsupported", "protocol_exhausted"]
    issue: ProtocolIssueCategory | None = None


# --- Agent context / result ---

@dataclass
class AgentContext:
    task: str
    profile: UserProfile
    chat_id: int
    user_id: int = 0
    catalog_summaries: list[SkillSummary] = field(default_factory=list)
    active_skill: SkillSpec | None = None
    messages: list[dict] = field(default_factory=list)
    iteration: int = 0
    tools_used: list[str] = field(default_factory=list)
    phase: AgentPhase = AgentPhase.SELECTION
    selection_retry_used: bool = False
    execution_retry_used: bool = False
    protocol_version: int = 2

    def with_messages(self, messages: list[dict]) -> AgentContext:
        return AgentContext(
            task=self.task,
            profile=self.profile,
            chat_id=self.chat_id,
            user_id=self.user_id,
            catalog_summaries=self.catalog_summaries,
            active_skill=self.active_skill,
            messages=messages,
            iteration=self.iteration,
            tools_used=list(self.tools_used),
            phase=self.phase,
            selection_retry_used=self.selection_retry_used,
            execution_retry_used=self.execution_retry_used,
            protocol_version=self.protocol_version,
        )


@dataclass
class AgentResult:
    answer: str | None = None
    clarification: str | None = None
    failure: AgentFailure | None = None
    tools_used: list[str] = field(default_factory=list)
