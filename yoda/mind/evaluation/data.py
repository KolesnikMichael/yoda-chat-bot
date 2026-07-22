"""Routing evaluation corpus and result Data contracts (TASK-020 / TASK-021)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yoda.mind.agent.data.agent_data import (
    AgentResult,
    ExecutionDecision,
    RequestConstraints,
    SelectionDecision,
    ToolCall,
)
from yoda.mind.agent.data.outcome_data import (
    AllowedClaim,
    DeliveryPayload,
    JobKind,
    NextStep,
    ProhibitedClaim,
    ResultKind,
    SafeFailureCategory,
    TerminalResultFacts,
    UserOperation,
)

type JsonValue = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)


class StageName(StrEnum):
    INTENT = "intent"
    SELECTION = "selection"
    PLANNING = "planning"
    EXECUTION = "execution"
    DELIVERY = "delivery"


class StageStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


STAGE_ORDER: tuple[StageName, ...] = (
    StageName.INTENT,
    StageName.SELECTION,
    StageName.PLANNING,
    StageName.EXECUTION,
    StageName.DELIVERY,
)


@dataclass(frozen=True)
class StructuralDiff:
    path: str
    expected: object
    observed: object


@dataclass(frozen=True)
class StageResult:
    stage: StageName
    turn_id: str
    status: StageStatus
    blocked_by: StageName | None
    diffs: tuple[StructuralDiff, ...]


@dataclass(frozen=True)
class StageCounts:
    passed: int
    failed: int
    applicable: int
    blocked: int


@dataclass(frozen=True)
class RoutingCaseResult:
    case_id: str
    stages: tuple[StageResult, ...]
    first_divergence: StageName | None
    passed: bool


@dataclass(frozen=True)
class RoutingEvaluationReport:
    corpus_version: str
    case_results: tuple[RoutingCaseResult, ...]
    stage_counts: dict[StageName, StageCounts]


@dataclass(frozen=True)
class CorpusIssue:
    case_id: str | None
    field_path: str
    message: str


class RecordedModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Literal["intent", "selection", "planning"]
    raw: str


class RecordedToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    output: str
    success: bool
    suspend: bool = False
    terminal_facts: TerminalResultFacts | None = None


class NotApplicableExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["not_applicable"]
    reason: Literal[
        "chat_route",
        "resume_bypass",
        "scheduled_bypass",
        "upstream_stop",
    ]


class TextExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_fragments: list[str] = Field(default_factory=list)
    prohibited_fragments: list[str] = Field(default_factory=list)


class IntentExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["intent"]
    route: Literal[
        "agent_task",
        "chat",
        "agent_resume",
        "rejected_fallback_chat",
    ]


class SelectionExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["selection"]
    mode: Literal["select_skill", "no_skill", "protocol_exhausted"]
    selected_skill: str | None = None
    distilled_task: TextExpectation | None = None
    request_constraints: RequestConstraints = Field(
        default_factory=RequestConstraints,
    )
    recovery: Literal["none", "corrected", "exhausted"] = "none"


class ExpectedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ExpectedToolBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matching: Literal["ordered", "unordered"]
    calls: list[ExpectedToolCall]


class PlanningExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["planning"]
    accepted_modes: list[Literal["call_tools", "finish", "fail"]]
    tool_batches: list[ExpectedToolBatch] = Field(default_factory=list)
    recovery: Literal["none", "corrected", "exhausted"] = "none"


class ExecutionExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["execution"]
    result: Literal["success", "failure", "clarification"]
    operation: UserOperation | None = None
    result_kind: ResultKind | None = None
    job_kind: JobKind | None = None
    scheduled_operation: UserOperation | None = None
    schedule: TextExpectation | None = None
    failure_category: SafeFailureCategory | None = None
    next_step: NextStep | None = None


class DeliveryExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["delivery"]
    status: Literal["success", "failure", "clarification"]
    facts: list[str] = Field(default_factory=list)
    allowed_claims: list[AllowedClaim] = Field(default_factory=list)
    prohibited_claims: list[ProhibitedClaim] = Field(default_factory=list)
    source_text: TextExpectation = Field(default_factory=TextExpectation)


StageExpectation = Annotated[
    IntentExpectation
    | NotApplicableExpectation
    | SelectionExpectation
    | PlanningExpectation
    | ExecutionExpectation
    | DeliveryExpectation,
    Field(discriminator="kind"),
]


class StageExpectations(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: IntentExpectation | NotApplicableExpectation
    selection: SelectionExpectation | NotApplicableExpectation
    planning: PlanningExpectation | NotApplicableExpectation
    execution: ExecutionExpectation | NotApplicableExpectation
    delivery: DeliveryExpectation | NotApplicableExpectation


class RoutingMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str


class UserProfileFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferred_name: str = ""
    location: str = ""
    timezone: str = ""
    skill_preferences: dict[str, list[str]] = Field(default_factory=dict)


class TurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    recent_messages: list[RoutingMessage] = Field(default_factory=list)
    forced_skill: str | None = None
    request_constraints: RequestConstraints = Field(
        default_factory=RequestConstraints,
    )
    skill_name: str | None = None
    distilled_task: str | None = None


class RoutingTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    event: Literal["message", "resume", "scheduled_task"]
    input: TurnInput
    fixed_now_utc: datetime
    profile: UserProfileFixture
    model_responses: list[RecordedModelResponse]
    tool_results: list[RecordedToolResult]
    expected: StageExpectations


class RoutingCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    language: str
    purpose: str
    turns: list[RoutingTurn]

    @model_validator(mode="after")
    def _unique_turn_ids(self) -> RoutingCase:
        ids = [turn.id for turn in self.turns]
        if len(ids) != len(set(ids)):
            raise ValueError("turn ids must be unique within a case")
        return self


class RoutingCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    corpus_version: str
    cases: list[RoutingCase]


@dataclass
class IntentObservation:
    route: Literal[
        "agent_task",
        "chat",
        "agent_resume",
        "rejected_fallback_chat",
    ]


@dataclass
class SelectionObservation:
    mode: Literal["select_skill", "no_skill", "protocol_exhausted"]
    decision: SelectionDecision | None = None
    recovery: Literal["none", "corrected", "exhausted"] = "none"


@dataclass
class PlanningObservation:
    decisions: list[ExecutionDecision] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    recovery: Literal["none", "corrected", "exhausted"] = "none"


@dataclass
class ExecutionObservation:
    agent_result: AgentResult | None = None


@dataclass
class DeliveryObservation:
    payload: DeliveryPayload | None = None


@dataclass
class TurnObservation:
    turn_id: str
    intent: IntentObservation | None = None
    selection: SelectionObservation | None = None
    planning: PlanningObservation | None = None
    execution: ExecutionObservation | None = None
    delivery: DeliveryObservation | None = None


@dataclass
class RoutingObservation:
    case_id: str
    turns: list[TurnObservation] = field(default_factory=list)

    def turn(self, turn_id: str) -> TurnObservation | None:
        for item in self.turns:
            if item.turn_id == turn_id:
                return item
        return None


class DiagnosticOutcome(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    EXHAUSTED = "exhausted"
    FAILED = "failed"
    BYPASSED = "bypassed"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class PromptIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_id: str
    prompt_hash: str


class StageDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: StageName
    outcome: DiagnosticOutcome
    model_id: str | None = None
    prompts: tuple[PromptIdentity, ...] = ()
    detail: str | None = None


class LiveExclusionReason(StrEnum):
    FORCED_MALFORMED_INTENT = "forced_malformed_intent"
    FORCED_SELECTION_RECOVERY = "forced_selection_recovery"
    FORCED_PLANNING_RECOVERY = "forced_planning_recovery"
    FORCED_PROTOCOL_EXHAUSTION = "forced_protocol_exhaustion"


class LiveCaseExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    reason: LiveExclusionReason


class LiveRunStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class OperationalErrorCategory(StrEnum):
    PROVIDER_AUTH = "provider_auth"
    PROVIDER_RATE_LIMIT = "provider_rate_limit"
    PROVIDER_ERROR = "provider_error"
    FORBIDDEN_SIDE_EFFECT = "forbidden_side_effect"
    INTERRUPTED = "interrupted"
    INTERNAL = "internal"


class LiveStageMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: StageName
    passed: int
    failed: int
    applicable: int
    blocked: int
    pass_rate: float


class LiveEvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_schema_version: Literal[1]
    run_id: str
    started_at_utc: datetime
    ended_at_utc: datetime
    status: LiveRunStatus
    corpus_schema_version: int
    corpus_version: str
    case_filter: str | None
    model_id: str
    prompts_used: list[PromptIdentity]
    exclusions: list[LiveCaseExclusion]
    case_results: list[RoutingCaseResult]
    incomplete_case_ids: list[str]
    unattempted_case_ids: list[str]
    stage_metrics: list[LiveStageMetrics]
    attempted: int
    passed: int
    failed: int
    excluded: int
    incomplete: int
    operational_errors: list[OperationalErrorCategory]
