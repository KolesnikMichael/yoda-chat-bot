"""RoutingEvaluationCore scorer tests (TASK-020)."""

from __future__ import annotations

from yoda.mind.agent.data.agent_data import (
    AgentResult,
    ExecutionDecision,
    RequestConstraints,
    SelectionDecision,
    ToolCall,
)
from yoda.mind.agent.data.outcome_data import (
    AllowedClaim,
    ClarificationResult,
    DeliveryPayload,
    ExecutionOutcome,
    JobKind,
    NextStep,
    OutcomeStatus,
    ProhibitedClaim,
    ResultKind,
    SafeFailureCategory,
    UserOperation,
)
from yoda.mind.agent.core.delivery_core import DeliveryCore
from yoda.mind.evaluation.core import RoutingEvaluationCore
from yoda.mind.evaluation.data import (
    DeliveryExpectation,
    DeliveryObservation,
    ExecutionExpectation,
    ExecutionObservation,
    ExpectedToolBatch,
    ExpectedToolCall,
    IntentExpectation,
    IntentObservation,
    NotApplicableExpectation,
    PlanningExpectation,
    PlanningObservation,
    RoutingCase,
    RoutingObservation,
    SelectionExpectation,
    SelectionObservation,
    StageExpectations,
    StageName,
    StageStatus,
    TextExpectation,
    TurnObservation,
    UserProfileFixture,
)


def _chat_case() -> RoutingCase:
    return RoutingCase(
        id="case",
        language="en",
        purpose="test",
        turns=[],
    )


def test_tool_argument_subset_and_ordered_batch() -> None:
    expected = {"query": "weather", "include_domains": ["accuweather.com"]}
    observed = {
        "query": "weather in SPb",
        "include_domains": ["accuweather.com"],
        "max_results": 5,
    }
    assert RoutingEvaluationCore.argument_is_subset(expected, observed)
    batches = [
        ExpectedToolBatch(
            matching="ordered",
            calls=[
                ExpectedToolCall(tool_name="web_search", arguments={"query": "a"}),
                ExpectedToolCall(
                    tool_name="schedule_task",
                    arguments={"skill_name": "search_web"},
                ),
            ],
        ),
    ]
    calls = [
        ToolCall(tool_name="web_search", arguments={"query": "a"}),
        ToolCall(
            tool_name="schedule_task",
            arguments={"skill_name": "search_web", "distilled_task": "x"},
        ),
    ]
    assert RoutingEvaluationCore.tool_batches_match(batches, calls) == []


def test_blocked_stage_not_scored_as_pass() -> None:
    case = RoutingCase(
        id="blocked",
        language="en",
        purpose="blocked downstream",
        turns=[
            {
                "id": "t1",
                "event": "message",
                "input": {"text": "do work"},
                "fixed_now_utc": "2026-07-20T12:00:00+00:00",
                "profile": {},
                "model_responses": [],
                "tool_results": [],
                "expected": {
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools"],
                    },
                    "execution": {
                        "kind": "execution",
                        "result": "success",
                    },
                    "delivery": {
                        "kind": "delivery",
                        "status": "success",
                    },
                },
            },
        ],
    )
    observation = RoutingObservation(
        case_id="blocked",
        turns=[
            TurnObservation(
                turn_id="t1",
                intent=IntentObservation(route="chat"),
            ),
        ],
    )
    result = RoutingEvaluationCore.score_case(case, observation)
    blocked = [
        stage
        for stage in result.stages
        if stage.status is StageStatus.BLOCKED
    ]
    assert blocked
    assert result.first_divergence is StageName.INTENT
    assert not result.passed


def test_emitted_downstream_stage_is_scored_after_divergence() -> None:
    case = RoutingCase(
        id="observed-after-divergence",
        language="en",
        purpose="score emitted downstream stages",
        turns=[
            {
                "id": "t1",
                "event": "message",
                "input": {"text": "do work"},
                "fixed_now_utc": "2026-07-20T12:00:00+00:00",
                "profile": {},
                "model_responses": [],
                "tool_results": [],
                "expected": {
                    "intent": {"kind": "intent", "route": "agent_task"},
                    "selection": {
                        "kind": "selection",
                        "mode": "select_skill",
                        "selected_skill": "search_web",
                    },
                    "planning": {
                        "kind": "planning",
                        "accepted_modes": ["call_tools"],
                    },
                    "execution": {
                        "kind": "not_applicable",
                        "reason": "upstream_stop",
                    },
                    "delivery": {
                        "kind": "not_applicable",
                        "reason": "upstream_stop",
                    },
                },
            },
        ],
    )
    observation = RoutingObservation(
        case_id=case.id,
        turns=[
            TurnObservation(
                turn_id="t1",
                intent=IntentObservation(route="chat"),
                selection=SelectionObservation(
                    mode="select_skill",
                    decision=SelectionDecision(
                        mode="select_skill",
                        selected_skill="search_web",
                        distilled_task="do work",
                    ),
                ),
            ),
        ],
    )

    result = RoutingEvaluationCore.score_case(case, observation)
    selection = next(
        stage for stage in result.stages if stage.stage is StageName.SELECTION
    )
    planning = next(
        stage for stage in result.stages if stage.stage is StageName.PLANNING
    )

    assert selection.status is StageStatus.PASS
    assert planning.status is StageStatus.BLOCKED


def test_aggregate_and_summary_redacted() -> None:
    from yoda.mind.evaluation.data import (
        RoutingCaseResult,
        StageResult,
        StructuralDiff,
    )

    case_result = RoutingCaseResult(
        case_id="c1",
        stages=(
            StageResult(
                stage=StageName.INTENT,
                turn_id="t1",
                status=StageStatus.FAIL,
                blocked_by=None,
                diffs=(
                    StructuralDiff(
                        path="intent.route",
                        expected="agent_task",
                        observed="private user text",
                    ),
                ),
            ),
        ),
        first_divergence=StageName.INTENT,
        passed=False,
    )
    report = RoutingEvaluationCore.aggregate("1.0.0", [case_result])
    summary = RoutingEvaluationCore.format_summary(report)
    assert "corpus_version=1.0.0" in summary
    assert "case_id=c1" in summary
    assert "cases: passed=0 failed=1 total=1" in summary
    assert "stage_counts:" in summary
    assert "private user text" not in summary
    debug_summary = RoutingEvaluationCore.format_summary(
        report,
        include_values=True,
    )
    assert "private user text" in debug_summary


def test_aggregate_counts_each_case_once_per_stage() -> None:
    from yoda.mind.evaluation.data import RoutingCaseResult, StageResult

    case_result = RoutingCaseResult(
        case_id="multi-turn",
        stages=(
            StageResult(
                stage=StageName.INTENT,
                turn_id="t1",
                status=StageStatus.PASS,
                blocked_by=None,
                diffs=(),
            ),
            StageResult(
                stage=StageName.INTENT,
                turn_id="t2",
                status=StageStatus.PASS,
                blocked_by=None,
                diffs=(),
            ),
        ),
        first_divergence=None,
        passed=True,
    )

    report = RoutingEvaluationCore.aggregate("1.0.0", [case_result])

    assert report.stage_counts[StageName.INTENT].passed == 1
    assert report.stage_counts[StageName.INTENT].applicable == 1


def test_prohibited_claim_negative_fails_delivery() -> None:
    outcome = ExecutionOutcome(
        operation=UserOperation.SCHEDULE_WORK,
        status=OutcomeStatus.SUCCESS,
        summary="Scheduled recurring lookup",
        result_kind=ResultKind.SCHEDULED_JOB,
        job_kind=JobKind.TASK,
        scheduled_operation=UserOperation.RETRIEVE_INFORMATION,
        schedule="0 8 * * * Europe/Moscow",
    )
    payload = DeliveryCore.build_payload(outcome)
    mutated = DeliveryPayload(
        status=payload.status,
        operation=payload.operation,
        source_text=payload.source_text,
        facts=payload.facts,
        allowed_claims=payload.allowed_claims,
        prohibited_claims=tuple(
            claim
            for claim in payload.prohibited_claims
            if claim is not ProhibitedClaim.FUTURE_RESULT
        ),
        next_step=payload.next_step,
        language_policy=payload.language_policy,
    )
    expectation = DeliveryExpectation(
        kind="delivery",
        status="success",
        prohibited_claims=[ProhibitedClaim.FUTURE_RESULT],
    )
    diffs = RoutingEvaluationCore._score_delivery(
        expectation,
        DeliveryObservation(payload=mutated),
    )
    assert diffs


def test_extra_delivery_claim_fails_exact_claim_scoring() -> None:
    outcome = ExecutionOutcome(
        operation=UserOperation.RETRIEVE_INFORMATION,
        status=OutcomeStatus.SUCCESS,
        summary="Weather retrieved",
        result_kind=ResultKind.INFORMATION,
    )
    payload = DeliveryCore.build_payload(outcome)
    mutated = DeliveryPayload(
        status=payload.status,
        operation=payload.operation,
        source_text=payload.source_text,
        facts=payload.facts,
        allowed_claims=(
            *payload.allowed_claims,
            AllowedClaim.DYNAMIC_OPERATION_SCHEDULED,
        ),
        prohibited_claims=payload.prohibited_claims,
        next_step=payload.next_step,
        language_policy=payload.language_policy,
    )
    expectation = DeliveryExpectation(
        kind="delivery",
        status="success",
        allowed_claims=list(payload.allowed_claims),
        prohibited_claims=list(payload.prohibited_claims),
    )

    diffs = RoutingEvaluationCore._score_delivery(
        expectation,
        DeliveryObservation(payload=mutated),
    )

    assert any(diff.path == "delivery.allowed_claims" for diff in diffs)


def test_internal_detail_marker_fails_delivery_scoring() -> None:
    payload = DeliveryPayload(
        status="failure",
        operation=UserOperation.REQUESTED_WORK,
        source_text="Provider schema error leaked",
        facts=(),
        allowed_claims=(AllowedClaim.SAFE_LIMITATION,),
        prohibited_claims=(
            ProhibitedClaim.INTERNAL_DETAILS,
            ProhibitedClaim.UNPROVED_SIDE_EFFECT,
        ),
        next_step=NextStep.TRY_LATER,
        language_policy="match_recent_user",
    )
    expectation = DeliveryExpectation(
        kind="delivery",
        status="failure",
        allowed_claims=list(payload.allowed_claims),
        prohibited_claims=list(payload.prohibited_claims),
        source_text=TextExpectation(prohibited_fragments=["provider schema"]),
    )

    diffs = RoutingEvaluationCore._score_delivery(
        expectation,
        DeliveryObservation(payload=payload),
    )

    assert any(diff.path == "delivery.source_text" for diff in diffs)


def test_repeatability_same_inputs_same_scores() -> None:
    case = RoutingCase(
        id="repeat",
        language="en",
        purpose="repeat",
        turns=[
            {
                "id": "t1",
                "event": "message",
                "input": {"text": "hello"},
                "fixed_now_utc": "2026-07-20T12:00:00+00:00",
                "profile": {},
                "model_responses": [],
                "tool_results": [],
                "expected": {
                    "intent": {"kind": "intent", "route": "chat"},
                    "selection": {"kind": "not_applicable", "reason": "chat_route"},
                    "planning": {"kind": "not_applicable", "reason": "chat_route"},
                    "execution": {"kind": "not_applicable", "reason": "chat_route"},
                    "delivery": {"kind": "not_applicable", "reason": "chat_route"},
                },
            },
        ],
    )
    observation = RoutingObservation(
        case_id="repeat",
        turns=[TurnObservation(turn_id="t1", intent=IntentObservation(route="chat"))],
    )
    first = RoutingEvaluationCore.score_case(case, observation)
    second = RoutingEvaluationCore.score_case(case, observation)
    assert first == second
