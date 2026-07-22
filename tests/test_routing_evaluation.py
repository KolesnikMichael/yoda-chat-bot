"""Deterministic routing evaluation CI gate (TASK-020)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from yoda.mind.agent.skills.catalog import SkillCatalog
from yoda.mind.evaluation.core import RoutingEvaluationCore
from yoda.mind.evaluation.corpus_provider import RoutingCorpusProvider
from tests.routing_evaluation.fakes import RecordedLLMApi
from tests.routing_evaluation.harness import PRODUCTION_SKILLS_DIR, RoutingEvaluation

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "routing_evaluation" / "corpus-v1.json"
)


@pytest.mark.asyncio
async def test_recorded_llm_consumes_staged_responses_in_order() -> None:
    from yoda.mind.cognition import IntentClassification
    from yoda.mind.evaluation.data import RecordedModelResponse

    api = RecordedLLMApi(
        [RecordedModelResponse(stage="intent", raw='{"intent": "chat"}')],
    )
    result = await api.parse_chat_async("m", [], IntentClassification)
    assert result.intent == "chat"
    api.assert_fully_consumed()


@pytest.mark.asyncio
async def test_recorded_llm_preserves_structured_parse_error() -> None:
    from yoda.mind.evaluation.data import RecordedModelResponse
    from yoda.mind.perception.language import LanguageProvider, StructuredOutputError
    from yoda.mind.agent.data.agent_data import SelectionDecision

    language = LanguageProvider(
        {"model_name": "evaluation-model"},
        RecordedLLMApi(
            [RecordedModelResponse(stage="selection", raw="{bad-json")],
        ),
    )

    with pytest.raises(StructuredOutputError):
        await language.parse_structured([], SelectionDecision)


@pytest.mark.asyncio
async def test_recorded_tool_provider_returns_fixture_and_captures_call() -> None:
    from yoda.mind.agent.data.agent_data import ToolCall
    from yoda.mind.evaluation.data import RecordedToolResult
    from tests.routing_evaluation.fakes import RecordedToolProvider

    provider = RecordedToolProvider(
        [RecordedToolResult(tool_name="web_search", output="ok", success=True)],
    )
    call = ToolCall(tool_name="web_search", arguments={"query": "x"})
    result = await provider.execute(call)
    assert result.success
    assert provider.captured_calls == [call]


@pytest.mark.asyncio
async def test_evaluation_agent_captures_accepted_selection() -> None:
    from yoda.mind.agent.session_provider import AgentSessionProvider
    from yoda.mind.agent.tools.web_search_tool import WebSearchTool
    from yoda.mind.evaluation.data import RecordedModelResponse, TurnObservation
    from yoda.mind.memory.data.user_profile import UserProfile
    from yoda.mind.perception.language import LanguageProvider
    from tests.routing_evaluation.fakes import InMemoryStorageApi, RecordedLLMApi, RecordedToolProvider
    from tests.routing_evaluation.harness import _RecordedTool
    from yoda.mind.evaluation.observation import ObservingAgent

    turn_obs = TurnObservation(turn_id="t1")
    llm = RecordedLLMApi(
        [
            RecordedModelResponse(
                stage="selection",
                raw=(
                    '{"mode": "select_skill", "selected_skill": "search_web", '
                    '"distilled_task": "Find weather."}'
                ),
            ),
            RecordedModelResponse(
                stage="planning",
                raw='{"mode": "fail", "failure_reason": "unsupported"}',
            ),
        ],
    )
    language = LanguageProvider({"model_name": "eval"}, llm)
    tool_provider = RecordedToolProvider()
    tools = [
        _RecordedTool(
            "web_search",
            WebSearchTool.parameters_schema,
            tool_provider,
        ),
    ]
    agent = ObservingAgent(
        language_provider=language,
        tools=tools,
        skills_dir=PRODUCTION_SKILLS_DIR,
        session_provider=AgentSessionProvider(InMemoryStorageApi()),
        turn_observation=turn_obs,
    )
    await agent.run(task="weather", profile=UserProfile(), chat_id=1)
    assert turn_obs.selection is not None
    assert turn_obs.selection.mode == "select_skill"


@pytest.mark.asyncio
async def test_evaluation_mind_captures_delivery_payload() -> None:
    from yoda.mind.agent.data.agent_data import AgentResult
    from yoda.mind.agent.data.outcome_data import (
        ExecutionOutcome,
        OutcomeStatus,
        ResultKind,
        UserOperation,
    )
    from yoda.mind.evaluation.data import TurnObservation
    from yoda.mind.evaluation.observation import ObservingMind
    from tests.fakes import FakeCognitionProvider, FakeLanguageProvider, FakeMemoryProvider
    from yoda.mind.perception.perception import Perception
    from tests.fakes import FakeAudioProvider, FakeVisionProvider

    class _Agent:
        async def has_pending_session(self, chat_id: int) -> bool:
            return False

        async def run(self, **kwargs) -> AgentResult:
            return AgentResult(
                outcome=ExecutionOutcome(
                    operation=UserOperation.RETRIEVE_INFORMATION,
                    status=OutcomeStatus.SUCCESS,
                    summary="Done",
                    result_kind=ResultKind.INFORMATION,
                ),
            )

    turn_obs = TurnObservation(turn_id="t1")
    mind = ObservingMind(
        language_provider=FakeLanguageProvider(),
        perception=Perception(FakeAudioProvider(), FakeVisionProvider()),
        memory_provider=FakeMemoryProvider(),
        affect_provider=type("A", (), {"get_emotional_state": lambda self: __import__("yoda.mind.memory.data.emotional_state", fromlist=["EmotionalState"]).EmotionalState()})(),
        cognition_provider=FakeCognitionProvider("agent_task"),
        agent=_Agent(),
        turn_observation=turn_obs,
    )
    from yoda.mind.memory.data.pending_message import PendingMessage

    await mind.process_message_batch(
        1,
        [
            PendingMessage(
                user_id=1,
                message_id=1,
                user_info={"first_name": "U"},
                media_type="text",
                text="search",
            ),
        ],
    )
    assert turn_obs.delivery is not None
    assert turn_obs.delivery.payload is not None


@pytest.mark.asyncio
async def test_harness_runs_single_turn_chat_case() -> None:
    from yoda.mind.evaluation.corpus_provider import RoutingCorpusProvider

    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    chat_case = next(case for case in corpus.cases if case.id.endswith("chat-greeting"))
    harness = RoutingEvaluation()
    result = await harness.run_case(chat_case)
    assert result.passed


@pytest.mark.asyncio
async def test_july_20_regression_case() -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    case = next(
        case for case in corpus.cases
        if case.id == "july-20-recurring-spb-weather-accuweather"
    )
    harness = RoutingEvaluation()
    result = await harness.run_case(case)
    assert result.passed, RoutingEvaluationCore.format_summary(
        RoutingEvaluationCore.aggregate(corpus.corpus_version, [result]),
    )


@pytest.mark.asyncio
async def test_scheduling_contrast_cases_pass() -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    harness = RoutingEvaluation()
    case_ids = {
        "en-schedule-static-message",
        "en-delayed-dynamic-weather-check",
        "ru-relative-static-reminder",
        "july-20-recurring-spb-weather-accuweather",
    }

    for case in corpus.cases:
        if case.id in case_ids:
            result = await harness.run_case(case)
            assert result.passed, case.id


@pytest.mark.asyncio
async def test_domain_constraint_case_passes() -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    case = next(
        item
        for item in corpus.cases
        if item.id == "en-strict-constraint-overrides-preference"
    )

    result = await RoutingEvaluation().run_case(case)

    assert result.passed, RoutingEvaluationCore.format_summary(
        RoutingEvaluationCore.aggregate(corpus.corpus_version, [result]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id",
    [
        "en-selection-no-skill",
        "en-selection-protocol-corrected",
        "ru-selection-protocol-exhausted",
        "en-strict-constraint-overrides-preference",
        "ru-execution-protocol-exhausted",
        "en-execution-unsupported",
    ],
)
async def test_recovery_and_safe_failure_cases_pass(case_id: str) -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    case = next(item for item in corpus.cases if item.id == case_id)

    result = await RoutingEvaluation().run_case(case)

    assert result.passed, RoutingEvaluationCore.format_summary(
        RoutingEvaluationCore.aggregate(corpus.corpus_version, [result]),
    )


@pytest.mark.asyncio
async def test_clarification_suspend_resume_case() -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    case = next(case for case in corpus.cases if case.id == "en-clarification-suspend-resume")
    harness = RoutingEvaluation()
    result = await harness.run_case(case)
    assert result.passed, RoutingEvaluationCore.format_summary(
        RoutingEvaluationCore.aggregate(corpus.corpus_version, [result]),
    )


@pytest.mark.asyncio
async def test_harness_repeatability_same_case_same_score() -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)
    case = next(
        item for item in corpus.cases if item.id == "en-search-refinement"
    )
    harness = RoutingEvaluation()

    first = await harness.run_case(case)
    second = await harness.run_case(case)

    assert first == second


@pytest.mark.asyncio
async def test_unknown_case_filter_fails_before_execution() -> None:
    corpus = await RoutingCorpusProvider().load(FIXTURE_PATH)

    with pytest.raises(ValueError, match="unknown case id"):
        await RoutingEvaluation().run_corpus(corpus, case_id="missing-case")


@pytest.mark.asyncio
async def test_routing_evaluation_gate() -> None:
    case_filter = os.environ.get("ROUTING_EVAL_CASE")
    provider = RoutingCorpusProvider()
    corpus = await provider.load(FIXTURE_PATH)
    discovered = frozenset(
        summary.name for summary in SkillCatalog.load_catalog(PRODUCTION_SKILLS_DIR)
    )
    issues = RoutingEvaluationCore.validate_corpus(corpus, discovered)
    assert not issues, issues
    harness = RoutingEvaluation()
    report = await harness.run_corpus(corpus, case_id=case_filter)
    failures = [case for case in report.case_results if not case.passed]
    if failures:
        summary = RoutingEvaluationCore.format_summary(report)
        pytest.fail(summary)
