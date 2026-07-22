from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from yoda.mind.agent.data.outcome_data import (
    ClarificationResult,
    ExecutionOutcome,
    OutcomeEvidence,
    TerminalResultFacts,
)
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
    terminal_facts: TerminalResultFacts | None = None

    def __post_init__(self) -> None:
        if self.terminal_facts is not None and not self.success:
            raise ValueError("terminal_facts only allowed on successful ToolResult")


# --- Phase protocol (Pydantic for structured output) ---

class AgentPhase(StrEnum):
    SELECTION = "selection"
    EXECUTION = "execution"


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    arguments: dict


class RequestConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strict_source_domains: list[str] = Field(default_factory=list)
    soft_source_domains: list[str] = Field(default_factory=list)


class SelectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["select_skill", "no_skill"]
    selected_skill: str | None = None
    distilled_task: str | None = None
    reason: Literal["unsupported"] | None = None
    reasoning: str = ""
    request_constraints: RequestConstraints = Field(
        default_factory=RequestConstraints,
    )


class ExecutionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["call_tools", "finish", "fail"]
    tool_calls: list[ToolCallRequest] | None = None
    final_answer: str | None = None
    failure_reason: Literal["unsupported"] | None = None
    reasoning: str = ""


class ProtocolIssueCategory(StrEnum):
    MALFORMED_OUTPUT = "malformed_output"
    INVALID_MODE = "invalid_mode"
    UNKNOWN_SKILL = "unknown_skill"
    UNKNOWN_TOOL = "unknown_tool"
    ITERATION_LIMIT = "iteration_limit"
    INVALID_CONSTRAINT = "invalid_constraint"


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
    request_constraints: RequestConstraints = field(
        default_factory=RequestConstraints,
    )
    protocol_version: int = 4
    outcome_evidence: list[OutcomeEvidence] = field(default_factory=list)
    terminal_failure_pending: bool = False

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
            request_constraints=self.request_constraints,
            protocol_version=self.protocol_version,
            outcome_evidence=list(self.outcome_evidence),
            terminal_failure_pending=self.terminal_failure_pending,
        )


@dataclass(frozen=True)
class AgentResult:
    outcome: ExecutionOutcome | None = None
    clarification: ClarificationResult | None = None

    def __post_init__(self) -> None:
        has_outcome = self.outcome is not None
        has_clarification = self.clarification is not None
        if has_outcome == has_clarification:
            raise ValueError("AgentResult requires exactly one of outcome or clarification")
