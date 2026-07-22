"""Pure outcome evidence mapping, success authorization, and safe failures."""

from __future__ import annotations

from yoda.mind.agent.data.agent_data import AgentFailure, ToolResult
from yoda.mind.agent.data.outcome_data import (
    ExecutionOutcome,
    JobKind,
    NextStep,
    OutcomeEvidence,
    OutcomeStatus,
    ResultKind,
    SafeFailureCategory,
    TerminalResultFacts,
    UserOperation,
)

_SKILL_OPERATION: dict[str, UserOperation] = {
    "search_web": UserOperation.RETRIEVE_INFORMATION,
    "schedule_message": UserOperation.SCHEDULE_WORK,
    "create_picture": UserOperation.CREATE_PICTURE,
    "manage_jobs": UserOperation.MANAGE_SCHEDULED_JOBS,
    "manage_user_data": UserOperation.MANAGE_USER_DATA,
}

_TOOL_EVIDENCE: dict[str, tuple[UserOperation, ResultKind, bool]] = {
    "web_search": (UserOperation.RETRIEVE_INFORMATION, ResultKind.INFORMATION, False),
    "web_extract": (UserOperation.RETRIEVE_INFORMATION, ResultKind.INFORMATION, False),
    "schedule_message": (UserOperation.SCHEDULE_WORK, ResultKind.SCHEDULED_JOB, True),
    "schedule_task": (UserOperation.SCHEDULE_WORK, ResultKind.SCHEDULED_JOB, True),
    "send_picture": (UserOperation.CREATE_PICTURE, ResultKind.PICTURE_SENT, True),
    "text_to_image": (UserOperation.CREATE_PICTURE, ResultKind.INFORMATION, False),
    "image_to_text": (UserOperation.RETRIEVE_INFORMATION, ResultKind.INFORMATION, False),
    "list_jobs": (UserOperation.MANAGE_SCHEDULED_JOBS, ResultKind.JOB_STATE, False),
    "cancel_job": (UserOperation.MANAGE_SCHEDULED_JOBS, ResultKind.JOB_STATE, False),
    "delete_user_data": (UserOperation.MANAGE_USER_DATA, ResultKind.USER_DATA, True),
    "get_user_data": (UserOperation.MANAGE_USER_DATA, ResultKind.USER_DATA, False),
    "update_profile": (UserOperation.MANAGE_USER_DATA, ResultKind.USER_DATA, False),
}

_SAFE_SUMMARIES: dict[SafeFailureCategory, str] = {
    SafeFailureCategory.AMBIGUOUS: (
        "The request is unclear. Please clarify or rephrase what you need."
    ),
    SafeFailureCategory.TRANSIENT: (
        "Something went wrong temporarily. Please try again later."
    ),
    SafeFailureCategory.UNSUPPORTED: (
        "That request is outside what I can do here."
    ),
}

_FAILURE_NEXT_STEP: dict[SafeFailureCategory, NextStep] = {
    SafeFailureCategory.AMBIGUOUS: NextStep.CLARIFY_OR_REPHRASE,
    SafeFailureCategory.TRANSIENT: NextStep.TRY_LATER,
    SafeFailureCategory.UNSUPPORTED: NextStep.STATE_CAPABILITY_BOUNDARY,
}


class OutcomeCore:
    @staticmethod
    def operation_for_skill(skill_name: str) -> UserOperation:
        return _SKILL_OPERATION.get(skill_name, UserOperation.REQUESTED_WORK)

    @staticmethod
    def evidence_from_results(
        active_skill_name: str,
        results: list[ToolResult],
    ) -> list[OutcomeEvidence]:
        evidence: list[OutcomeEvidence] = []
        for result in results:
            if not result.success:
                continue
            if result.terminal_facts is not None:
                evidence.append(
                    OutcomeCore._evidence_from_terminal_facts(
                        active_skill_name,
                        result.terminal_facts,
                    ),
                )
                continue
            mapped = _TOOL_EVIDENCE.get(result.tool_name)
            if mapped is None:
                continue
            operation, result_kind, terminal = mapped
            evidence.append(
                OutcomeEvidence(
                    operation=operation,
                    result_kind=result_kind,
                    terminal=terminal,
                ),
            )
        return evidence

    @staticmethod
    def success_from_terminal(
        evidence: list[OutcomeEvidence],
    ) -> ExecutionOutcome:
        terminal = [item for item in evidence if item.terminal]
        if not terminal:
            return OutcomeCore.failure(
                UserOperation.REQUESTED_WORK,
                SafeFailureCategory.TRANSIENT,
            )
        item = terminal[-1]
        summary = item.safe_summary or "The requested work completed."
        return ExecutionOutcome(
            operation=item.operation,
            status=OutcomeStatus.SUCCESS,
            summary=summary,
            result_kind=item.result_kind,
            job_kind=item.job_kind,
            scheduled_operation=item.scheduled_operation,
            schedule=item.schedule,
        )

    @staticmethod
    def success_from_finish(
        active_skill_name: str,
        summary: str,
        evidence: list[OutcomeEvidence],
    ) -> ExecutionOutcome:
        operation = OutcomeCore.operation_for_skill(active_skill_name)
        relevant = [
            item
            for item in evidence
            if item.operation is operation or operation is UserOperation.REQUESTED_WORK
        ]
        if not relevant:
            return OutcomeCore.failure(operation, SafeFailureCategory.TRANSIENT)
        primary = relevant[-1]
        return ExecutionOutcome(
            operation=operation,
            status=OutcomeStatus.SUCCESS,
            summary=summary,
            result_kind=primary.result_kind,
            job_kind=primary.job_kind,
            scheduled_operation=primary.scheduled_operation,
            schedule=primary.schedule,
        )

    @staticmethod
    def failure_from_agent(
        failure: AgentFailure,
        operation: UserOperation,
    ) -> ExecutionOutcome:
        if failure.category == "unsupported":
            category = SafeFailureCategory.UNSUPPORTED
        else:
            category = SafeFailureCategory.TRANSIENT
        return OutcomeCore.failure(operation, category)

    @staticmethod
    def failure(
        operation: UserOperation,
        category: SafeFailureCategory,
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            operation=operation,
            status=OutcomeStatus.FAILURE,
            summary=_SAFE_SUMMARIES[category],
            failure_category=category,
            next_step=_FAILURE_NEXT_STEP[category],
        )

    @staticmethod
    def _evidence_from_terminal_facts(
        active_skill_name: str,
        facts: TerminalResultFacts,
    ) -> OutcomeEvidence:
        if facts.result_kind is ResultKind.SCHEDULED_JOB:
            operation = UserOperation.SCHEDULE_WORK
            scheduled_operation = None
            if facts.job_kind is JobKind.TASK:
                skill = facts.scheduled_skill_name or active_skill_name
                scheduled_operation = OutcomeCore.operation_for_skill(skill)
            return OutcomeEvidence(
                operation=operation,
                result_kind=facts.result_kind,
                terminal=True,
                safe_summary=facts.summary,
                job_kind=facts.job_kind,
                scheduled_operation=scheduled_operation,
                schedule=facts.schedule,
            )
        if facts.result_kind is ResultKind.PICTURE_SENT:
            return OutcomeEvidence(
                operation=UserOperation.CREATE_PICTURE,
                result_kind=facts.result_kind,
                terminal=True,
                safe_summary=facts.summary,
            )
        if facts.result_kind is ResultKind.USER_DATA:
            return OutcomeEvidence(
                operation=UserOperation.MANAGE_USER_DATA,
                result_kind=facts.result_kind,
                terminal=True,
                safe_summary=facts.summary,
            )
        if facts.result_kind is ResultKind.STORED_MESSAGE_DELIVERED:
            return OutcomeEvidence(
                operation=UserOperation.DELIVER_STORED_MESSAGE,
                result_kind=facts.result_kind,
                terminal=True,
                safe_summary=facts.summary,
            )
        return OutcomeEvidence(
            operation=OutcomeCore.operation_for_skill(active_skill_name),
            result_kind=facts.result_kind,
            terminal=True,
            safe_summary=facts.summary,
            job_kind=facts.job_kind,
            schedule=facts.schedule,
        )
