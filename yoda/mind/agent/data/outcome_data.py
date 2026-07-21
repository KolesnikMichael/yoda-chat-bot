"""Capability-neutral outcome, evidence, and delivery Data contracts (TASK-018)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class OutcomeStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class UserOperation(StrEnum):
    REQUESTED_WORK = "requested_work"
    RETRIEVE_INFORMATION = "retrieve_information"
    SCHEDULE_WORK = "schedule_work"
    CREATE_PICTURE = "create_picture"
    MANAGE_SCHEDULED_JOBS = "manage_scheduled_jobs"
    MANAGE_USER_DATA = "manage_user_data"
    DELIVER_STORED_MESSAGE = "deliver_stored_message"


class ResultKind(StrEnum):
    INFORMATION = "information"
    SCHEDULED_JOB = "scheduled_job"
    PICTURE_SENT = "picture_sent"
    JOB_STATE = "job_state"
    USER_DATA = "user_data"
    STORED_MESSAGE_DELIVERED = "stored_message_delivered"


class JobKind(StrEnum):
    MESSAGE = "message"
    TASK = "task"


class SafeFailureCategory(StrEnum):
    AMBIGUOUS = "ambiguous"
    TRANSIENT = "transient"
    UNSUPPORTED = "unsupported"


class NextStep(StrEnum):
    CLARIFY_OR_REPHRASE = "clarify_or_rephrase"
    TRY_LATER = "try_later"
    STATE_CAPABILITY_BOUNDARY = "state_capability_boundary"


class AllowedClaim(StrEnum):
    STORED_TEXT_SCHEDULED = "stored_text_scheduled"
    DYNAMIC_OPERATION_SCHEDULED = "dynamic_operation_scheduled"
    OPERATION_COMPLETED = "operation_completed"
    PICTURE_SENT = "picture_sent"
    STORED_TEXT_DELIVERED = "stored_text_delivered"
    SAFE_LIMITATION = "safe_limitation"


class ProhibitedClaim(StrEnum):
    LIVE_RECOMPUTATION = "live_recomputation"
    FUTURE_RESULT = "future_result"
    UNCREATED_JOB = "uncreated_job"
    UNPROVED_SIDE_EFFECT = "unproved_side_effect"
    INTERNAL_DETAILS = "internal_details"
    CHANGED_CERTAINTY = "changed_certainty"


_FAILURE_NEXT_STEP: dict[SafeFailureCategory, NextStep] = {
    SafeFailureCategory.AMBIGUOUS: NextStep.CLARIFY_OR_REPHRASE,
    SafeFailureCategory.TRANSIENT: NextStep.TRY_LATER,
    SafeFailureCategory.UNSUPPORTED: NextStep.STATE_CAPABILITY_BOUNDARY,
}


@dataclass(frozen=True)
class TerminalResultFacts:
    result_kind: ResultKind
    summary: str
    job_kind: JobKind | None = None
    scheduled_skill_name: str | None = None
    schedule: str | None = None

    def __post_init__(self) -> None:
        if self.result_kind is ResultKind.SCHEDULED_JOB:
            if self.job_kind is None:
                raise ValueError("scheduled_job terminal facts require job_kind")
        elif self.job_kind is not None:
            raise ValueError("job_kind is only valid for scheduled_job")
        if self.job_kind is JobKind.MESSAGE and self.scheduled_skill_name is not None:
            raise ValueError("message job facts must not carry scheduled_skill_name")


@dataclass(frozen=True)
class OutcomeEvidence:
    operation: UserOperation
    result_kind: ResultKind
    terminal: bool
    safe_summary: str | None = None
    job_kind: JobKind | None = None
    scheduled_operation: UserOperation | None = None
    schedule: str | None = None

    def __post_init__(self) -> None:
        if self.result_kind is ResultKind.SCHEDULED_JOB:
            if self.job_kind is None:
                raise ValueError("scheduled_job evidence requires job_kind")
        elif any(
            value is not None
            for value in (
                self.job_kind,
                self.scheduled_operation,
                self.schedule,
            )
        ):
            raise ValueError("schedule fields are only valid for scheduled_job")
        if (
            self.scheduled_operation is not None
            and self.job_kind is not JobKind.TASK
        ):
            raise ValueError("scheduled_operation is only valid for task jobs")


@dataclass(frozen=True)
class ExecutionOutcome:
    operation: UserOperation
    status: OutcomeStatus
    summary: str
    result_kind: ResultKind | None = None
    job_kind: JobKind | None = None
    scheduled_operation: UserOperation | None = None
    schedule: str | None = None
    failure_category: SafeFailureCategory | None = None
    next_step: NextStep | None = None

    def __post_init__(self) -> None:
        if self.status is OutcomeStatus.SUCCESS:
            if self.result_kind is None:
                raise ValueError("success requires result_kind")
            if self.failure_category is not None or self.next_step is not None:
                raise ValueError("success forbids failure_category and next_step")
            if self.result_kind is ResultKind.SCHEDULED_JOB:
                if self.job_kind is None:
                    raise ValueError("scheduled_job success requires job_kind")
            elif any(
                value is not None
                for value in (
                    self.job_kind,
                    self.scheduled_operation,
                    self.schedule,
                )
            ):
                raise ValueError("schedule fields are only valid for scheduled_job")
            if (
                self.scheduled_operation is not None
                and self.job_kind is not JobKind.TASK
            ):
                raise ValueError("scheduled_operation is only valid for task jobs")
            return

        if self.status is OutcomeStatus.FAILURE:
            if self.failure_category is None or self.next_step is None:
                raise ValueError("failure requires failure_category and next_step")
            expected = _FAILURE_NEXT_STEP[self.failure_category]
            if self.next_step is not expected:
                raise ValueError(
                    f"failure_category {self.failure_category} requires next_step {expected}",
                )
            if any(
                value is not None
                for value in (
                    self.result_kind,
                    self.job_kind,
                    self.scheduled_operation,
                    self.schedule,
                )
            ):
                raise ValueError("failure forbids result_kind, job_kind, schedule fields")
            return

        raise ValueError(f"unknown status: {self.status}")


@dataclass(frozen=True)
class ClarificationResult:
    question: str


@dataclass(frozen=True)
class StaticMessageDelivery:
    reminder_text: str


@dataclass(frozen=True)
class DeliveryPayload:
    status: Literal["success", "failure", "clarification"]
    operation: UserOperation
    source_text: str
    facts: tuple[str, ...]
    allowed_claims: tuple[AllowedClaim, ...]
    prohibited_claims: tuple[ProhibitedClaim, ...]
    next_step: NextStep | None
    language_policy: Literal["preserve_source", "match_recent_user"]
