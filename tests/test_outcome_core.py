"""Tests for outcome Data consistency and OutcomeCore (TASK-018)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from yoda.mind.agent.data.outcome_data import (
    DeliveryPayload,
    ExecutionOutcome,
    JobKind,
    NextStep,
    OutcomeStatus,
    ResultKind,
    SafeFailureCategory,
    UserOperation,
)


# --- Step 1.1: Data consistency / validation ---


class TestExecutionOutcomeConsistency:
    def test_success_requires_result_kind(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.SUCCESS,
                summary="done",
            )

    def test_success_forbids_failure_fields(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.SUCCESS,
                summary="done",
                result_kind=ResultKind.INFORMATION,
                failure_category=SafeFailureCategory.TRANSIENT,
            )

    def test_failure_requires_category_and_matching_next_step(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.FAILURE,
                summary="failed",
                failure_category=SafeFailureCategory.TRANSIENT,
            )
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.FAILURE,
                summary="failed",
                failure_category=SafeFailureCategory.TRANSIENT,
                next_step=NextStep.CLARIFY_OR_REPHRASE,
            )

    def test_failure_forbids_result_job_schedule_fields(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.FAILURE,
                summary="failed",
                result_kind=ResultKind.INFORMATION,
                failure_category=SafeFailureCategory.TRANSIENT,
                next_step=NextStep.TRY_LATER,
            )
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.SCHEDULE_WORK,
                status=OutcomeStatus.FAILURE,
                summary="failed",
                job_kind=JobKind.MESSAGE,
                failure_category=SafeFailureCategory.TRANSIENT,
                next_step=NextStep.TRY_LATER,
            )

    def test_job_kind_only_with_scheduled_job(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.RETRIEVE_INFORMATION,
                status=OutcomeStatus.SUCCESS,
                summary="ok",
                result_kind=ResultKind.INFORMATION,
                job_kind=JobKind.MESSAGE,
            )

    def test_message_job_may_not_carry_scheduled_operation(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.SCHEDULE_WORK,
                status=OutcomeStatus.SUCCESS,
                summary="ok",
                result_kind=ResultKind.SCHEDULED_JOB,
                job_kind=JobKind.MESSAGE,
                scheduled_operation=UserOperation.RETRIEVE_INFORMATION,
                schedule="in 1 hour",
            )

    def test_non_scheduled_result_forbids_schedule_fields(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.RETRIEVE_INFORMATION,
                status=OutcomeStatus.SUCCESS,
                summary="ok",
                result_kind=ResultKind.INFORMATION,
                schedule="tomorrow",
            )
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.RETRIEVE_INFORMATION,
                status=OutcomeStatus.SUCCESS,
                summary="ok",
                result_kind=ResultKind.INFORMATION,
                scheduled_operation=UserOperation.RETRIEVE_INFORMATION,
            )

    def test_scheduled_operation_requires_task_job(self) -> None:
        with pytest.raises(ValueError):
            ExecutionOutcome(
                operation=UserOperation.SCHEDULE_WORK,
                status=OutcomeStatus.SUCCESS,
                summary="ok",
                result_kind=ResultKind.SCHEDULED_JOB,
                job_kind=JobKind.MESSAGE,
                scheduled_operation=UserOperation.RETRIEVE_INFORMATION,
            )

    def test_valid_success_and_failure_construct(self) -> None:
        success = ExecutionOutcome(
            operation=UserOperation.SCHEDULE_WORK,
            status=OutcomeStatus.SUCCESS,
            summary="reminder set",
            result_kind=ResultKind.SCHEDULED_JOB,
            job_kind=JobKind.MESSAGE,
            schedule="in 1 hour",
        )
        assert success.job_kind is JobKind.MESSAGE
        failure = ExecutionOutcome(
            operation=UserOperation.REQUESTED_WORK,
            status=OutcomeStatus.FAILURE,
            summary="could not complete",
            failure_category=SafeFailureCategory.AMBIGUOUS,
            next_step=NextStep.CLARIFY_OR_REPHRASE,
        )
        assert failure.failure_category is SafeFailureCategory.AMBIGUOUS

    def test_task_job_may_carry_scheduled_operation(self) -> None:
        outcome = ExecutionOutcome(
            operation=UserOperation.SCHEDULE_WORK,
            status=OutcomeStatus.SUCCESS,
            summary="task scheduled",
            result_kind=ResultKind.SCHEDULED_JOB,
            job_kind=JobKind.TASK,
            scheduled_operation=UserOperation.RETRIEVE_INFORMATION,
            schedule="every day at 09:00",
        )
        assert outcome.scheduled_operation is UserOperation.RETRIEVE_INFORMATION


class TestOutcomeEvidenceConsistency:
    def test_non_scheduled_evidence_forbids_schedule_fields(self) -> None:
        from yoda.mind.agent.data.outcome_data import OutcomeEvidence

        with pytest.raises(ValueError):
            OutcomeEvidence(
                operation=UserOperation.RETRIEVE_INFORMATION,
                result_kind=ResultKind.INFORMATION,
                terminal=False,
                schedule="tomorrow",
            )
        with pytest.raises(ValueError):
            OutcomeEvidence(
                operation=UserOperation.RETRIEVE_INFORMATION,
                result_kind=ResultKind.INFORMATION,
                terminal=False,
                scheduled_operation=UserOperation.RETRIEVE_INFORMATION,
            )


class TestDeliveryPayloadValidation:
    def test_delivery_payload_constructs_with_claim_tuples(self) -> None:
        from yoda.mind.agent.data.outcome_data import (
            AllowedClaim,
            ProhibitedClaim,
        )

        payload = DeliveryPayload(
            status="success",
            operation=UserOperation.SCHEDULE_WORK,
            source_text="reminder set",
            facts=("result_kind=scheduled_job", "job_kind=message"),
            allowed_claims=(AllowedClaim.STORED_TEXT_SCHEDULED,),
            prohibited_claims=(ProhibitedClaim.LIVE_RECOMPUTATION,),
            next_step=None,
            language_policy="match_recent_user",
        )
        assert payload.status == "success"
        assert AllowedClaim.STORED_TEXT_SCHEDULED in payload.allowed_claims
        assert ProhibitedClaim.LIVE_RECOMPUTATION in payload.prohibited_claims


# --- Step 1.2: exclusive AgentResult / protocol-4 fields ---


class TestAgentResultExclusivity:
    def test_requires_exactly_one_of_outcome_or_clarification(self) -> None:
        from yoda.mind.agent.data.agent_data import AgentResult
        from yoda.mind.agent.data.outcome_data import ClarificationResult

        with pytest.raises(ValueError):
            AgentResult()
        with pytest.raises(ValueError):
            AgentResult(
                outcome=ExecutionOutcome(
                    operation=UserOperation.REQUESTED_WORK,
                    status=OutcomeStatus.FAILURE,
                    summary="x",
                    failure_category=SafeFailureCategory.TRANSIENT,
                    next_step=NextStep.TRY_LATER,
                ),
                clarification=ClarificationResult(question="what?"),
            )

    def test_outcome_only_and_clarification_only_construct(self) -> None:
        from yoda.mind.agent.data.agent_data import AgentResult
        from yoda.mind.agent.data.outcome_data import ClarificationResult

        result = AgentResult(
            outcome=ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.FAILURE,
                summary="x",
                failure_category=SafeFailureCategory.TRANSIENT,
                next_step=NextStep.TRY_LATER,
            ),
        )
        assert result.clarification is None
        clarified = AgentResult(clarification=ClarificationResult(question="when?"))
        assert clarified.outcome is None

    def test_agent_result_is_immutable_after_validation(self) -> None:
        from yoda.mind.agent.data.agent_data import AgentResult

        result = AgentResult(
            outcome=ExecutionOutcome(
                operation=UserOperation.REQUESTED_WORK,
                status=OutcomeStatus.FAILURE,
                summary="x",
                failure_category=SafeFailureCategory.TRANSIENT,
                next_step=NextStep.TRY_LATER,
            ),
        )

        with pytest.raises(FrozenInstanceError):
            result.outcome = None

    def test_execution_decision_accepts_fail_unsupported(self) -> None:
        from yoda.mind.agent.data.agent_data import ExecutionDecision

        decision = ExecutionDecision(mode="fail", failure_reason="unsupported")
        assert decision.mode == "fail"
        assert decision.failure_reason == "unsupported"

    def test_tool_result_rejects_terminal_facts_on_failure(self) -> None:
        from yoda.mind.agent.data.agent_data import ToolResult
        from yoda.mind.agent.data.outcome_data import TerminalResultFacts

        with pytest.raises(ValueError):
            ToolResult(
                tool_name="schedule_message",
                output="err",
                success=False,
                terminal_facts=TerminalResultFacts(
                    result_kind=ResultKind.SCHEDULED_JOB,
                    summary="x",
                    job_kind=JobKind.MESSAGE,
                ),
            )

    def test_agent_context_defaults_protocol_4_and_empty_evidence(self) -> None:
        from yoda.mind.agent.data.agent_data import AgentContext
        from yoda.mind.memory.data.user_profile import UserProfile

        ctx = AgentContext(task="t", profile=UserProfile(), chat_id=1)
        assert ctx.protocol_version == 4
        assert ctx.outcome_evidence == []
        copied = ctx.with_messages([{"role": "user", "content": "hi"}])
        assert copied.outcome_evidence == []
        assert copied.protocol_version == 4


# --- Stage 2: OutcomeCore ---


class TestOutcomeCoreEvidenceAndSuccess:
    def test_evidence_from_results_skips_failures_and_maps_search(self) -> None:
        from yoda.mind.agent.core.outcome_core import OutcomeCore
        from yoda.mind.agent.data.agent_data import ToolResult

        evidence = OutcomeCore.evidence_from_results(
            "search_web",
            [
                ToolResult("web_search", "ok", True),
                ToolResult("web_search", "boom", False),
            ],
        )
        assert len(evidence) == 1
        assert evidence[0].operation is UserOperation.RETRIEVE_INFORMATION
        assert evidence[0].result_kind is ResultKind.INFORMATION
        assert evidence[0].terminal is False

    def test_evidence_from_terminal_facts_message_and_task(self) -> None:
        from yoda.mind.agent.core.outcome_core import OutcomeCore
        from yoda.mind.agent.data.agent_data import ToolResult
        from yoda.mind.agent.data.outcome_data import TerminalResultFacts

        message_facts = TerminalResultFacts(
            result_kind=ResultKind.SCHEDULED_JOB,
            summary="Reminder scheduled.",
            job_kind=JobKind.MESSAGE,
            schedule="in 60 minutes",
        )
        task_facts = TerminalResultFacts(
            result_kind=ResultKind.SCHEDULED_JOB,
            summary="Task scheduled.",
            job_kind=JobKind.TASK,
            scheduled_skill_name="search_web",
            schedule="every day at 09:00 Europe/Moscow",
        )
        evidence = OutcomeCore.evidence_from_results(
            "schedule_message",
            [
                ToolResult(
                    "schedule_message",
                    "ok",
                    True,
                    terminal_facts=message_facts,
                ),
            ],
        )
        assert evidence[0].job_kind is JobKind.MESSAGE
        assert evidence[0].terminal is True
        assert evidence[0].scheduled_operation is None

        task_evidence = OutcomeCore.evidence_from_results(
            "search_web",
            [
                ToolResult(
                    "schedule_task",
                    "ok",
                    True,
                    terminal_facts=task_facts,
                ),
            ],
        )
        assert task_evidence[0].job_kind is JobKind.TASK
        assert task_evidence[0].scheduled_operation is UserOperation.RETRIEVE_INFORMATION

    def test_success_from_terminal_uses_typed_facts(self) -> None:
        from yoda.mind.agent.core.outcome_core import OutcomeCore
        from yoda.mind.agent.data.outcome_data import OutcomeEvidence

        evidence = [
            OutcomeEvidence(
                operation=UserOperation.SCHEDULE_WORK,
                result_kind=ResultKind.SCHEDULED_JOB,
                terminal=True,
                safe_summary="Reminder scheduled.",
                job_kind=JobKind.MESSAGE,
                schedule="in 60 minutes",
            ),
        ]
        outcome = OutcomeCore.success_from_terminal(evidence)
        assert outcome.status is OutcomeStatus.SUCCESS
        assert outcome.job_kind is JobKind.MESSAGE
        assert outcome.result_kind is ResultKind.SCHEDULED_JOB
        assert outcome.summary == "Reminder scheduled."

    def test_success_from_finish_requires_relevant_evidence(self) -> None:
        from yoda.mind.agent.core.outcome_core import OutcomeCore
        from yoda.mind.agent.data.outcome_data import OutcomeEvidence

        empty = OutcomeCore.success_from_finish("search_web", "All done.", [])
        assert empty.status is OutcomeStatus.FAILURE
        assert empty.failure_category is SafeFailureCategory.TRANSIENT

        ok = OutcomeCore.success_from_finish(
            "search_web",
            "Here is the weather.",
            [
                OutcomeEvidence(
                    operation=UserOperation.RETRIEVE_INFORMATION,
                    result_kind=ResultKind.INFORMATION,
                    terminal=False,
                    safe_summary=None,
                ),
            ],
        )
        assert ok.status is OutcomeStatus.SUCCESS
        assert ok.result_kind is ResultKind.INFORMATION
        assert ok.summary == "Here is the weather."
        assert ok.job_kind is None


class TestOutcomeCoreFailure:
    def test_failure_from_agent_maps_categories(self) -> None:
        from yoda.mind.agent.core.outcome_core import OutcomeCore
        from yoda.mind.agent.data.agent_data import (
            AgentFailure,
            AgentPhase,
            ProtocolIssueCategory,
        )

        unsupported = OutcomeCore.failure_from_agent(
            AgentFailure(stage=AgentPhase.SELECTION, category="unsupported"),
            UserOperation.REQUESTED_WORK,
        )
        assert unsupported.failure_category is SafeFailureCategory.UNSUPPORTED
        assert unsupported.next_step is NextStep.STATE_CAPABILITY_BOUNDARY
        assert "skill" not in unsupported.summary.lower()

        exhausted = OutcomeCore.failure_from_agent(
            AgentFailure(
                stage=AgentPhase.EXECUTION,
                category="protocol_exhausted",
                issue=ProtocolIssueCategory.MALFORMED_OUTPUT,
            ),
            UserOperation.RETRIEVE_INFORMATION,
        )
        assert exhausted.failure_category is SafeFailureCategory.TRANSIENT
        assert exhausted.next_step is NextStep.TRY_LATER
        assert "protocol" not in exhausted.summary.lower()
        assert "schema" not in exhausted.summary.lower()

    def test_failure_ambiguous_transient_unsupported(self) -> None:
        from yoda.mind.agent.core.outcome_core import OutcomeCore

        ambiguous = OutcomeCore.failure(
            UserOperation.REQUESTED_WORK,
            SafeFailureCategory.AMBIGUOUS,
        )
        assert ambiguous.next_step is NextStep.CLARIFY_OR_REPHRASE
        transient = OutcomeCore.failure(
            UserOperation.CREATE_PICTURE,
            SafeFailureCategory.TRANSIENT,
        )
        assert transient.next_step is NextStep.TRY_LATER
        unsupported = OutcomeCore.failure(
            UserOperation.REQUESTED_WORK,
            SafeFailureCategory.UNSUPPORTED,
        )
        assert unsupported.next_step is NextStep.STATE_CAPABILITY_BOUNDARY
        for outcome in (ambiguous, transient, unsupported):
            assert outcome.status is OutcomeStatus.FAILURE
            blob = outcome.summary.lower()
            for marker in ("tool", "skill", "schema", "provider", "exception"):
                assert marker not in blob
