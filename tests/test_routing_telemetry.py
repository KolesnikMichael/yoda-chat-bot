"""RoutingTelemetryCore and production stage diagnostics (TASK-021)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.fakes import FakeLanguageProvider as MindFakeLanguage
from tests.test_agent import (
    FakeLanguageProvider as AgentFakeLanguage,
    FakeStorageApi,
    FakeTool,
    _call_tools,
    _finish,
    _select,
)
from yoda.mind.agent.agent import Agent
from yoda.mind.agent.data.agent_data import ToolCallRequest
from yoda.mind.agent.data.outcome_data import (
    SafeFailureCategory,
    UserOperation,
)
from yoda.mind.agent.core.outcome_core import OutcomeCore
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.tools.ask_user_tool import AskUserTool
from yoda.mind.cognition import CognitionProvider, IntentClassification
from yoda.mind.data.routing_context import RoutingContext
from yoda.mind.evaluation.data import (
    DiagnosticOutcome,
    PromptIdentity,
    StageDiagnostic,
    StageName,
)
from yoda.mind.evaluation.telemetry_core import RoutingTelemetryCore
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.mind import Mind
from yoda.mind.perception.language import StructuredOutputError

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "skills"


def _diagnostic(**overrides: object) -> StageDiagnostic:
    base: dict[str, object] = dict(
        stage=StageName.INTENT,
        outcome=DiagnosticOutcome.SUCCESS,
        model_id="gpt-test",
        prompts=(
            PromptIdentity(prompt_id="intent_classifier/v1", prompt_hash="abc123"),
        ),
        detail="agent_task",
    )
    base.update(overrides)
    return StageDiagnostic(**base)  # type: ignore[arg-type]


def test_format_info_includes_stage_outcome_model_and_prompts() -> None:
    text = RoutingTelemetryCore.format_info(_diagnostic())
    assert "stage=intent" in text
    assert "outcome=success" in text
    assert "model_id=gpt-test" in text
    assert "prompt_id=intent_classifier/v1" in text
    assert "prompt_hash=abc123" in text
    assert "detail=agent_task" in text


def test_format_warning_marks_warning_level_token() -> None:
    text = RoutingTelemetryCore.format_warning(
        _diagnostic(outcome=DiagnosticOutcome.FAILED, detail="protocol_exhausted"),
    )
    assert "outcome=failed" in text
    assert "detail=protocol_exhausted" in text


def test_formatters_omit_user_content_and_prompt_bodies() -> None:
    leaked = "Please remind me to buy milk at 5pm"
    text = RoutingTelemetryCore.format_info(_diagnostic(detail="rejected"))
    assert leaked not in text
    assert "You are a" not in text
    assert "tool_args" not in text
    assert "source_text" not in text


def test_multi_prompt_retention_in_formatted_record() -> None:
    text = RoutingTelemetryCore.format_info(
        _diagnostic(
            stage=StageName.EXECUTION,
            prompts=(
                PromptIdentity(prompt_id="skill_executor/v1", prompt_hash="h1"),
                PromptIdentity(prompt_id="search_web/v1", prompt_hash="h2"),
            ),
            detail=None,
        ),
    )
    assert "prompt_id=skill_executor/v1" in text
    assert "prompt_hash=h1" in text
    assert "prompt_id=search_web/v1" in text
    assert "prompt_hash=h2" in text


@pytest.mark.asyncio
async def test_cognition_intent_success_emits_privacy_safe_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = AsyncMock()
    llm.model_name = "intent-model"
    llm.parse_structured = AsyncMock(
        return_value=IntentClassification(intent="agent_task"),
    )
    provider = CognitionProvider(llm)
    routing = RoutingContext(
        current_user_text="secret user request about milk",
        recent_messages=[],
    )
    with caplog.at_level(logging.INFO, logger="yoda.mind.cognition"):
        assert await provider.classify_intent(routing) == "agent_task"
    records = [r for r in caplog.records if r.name == "yoda.mind.cognition"]
    info = [r for r in records if r.levelno == logging.INFO]
    assert info
    message = info[-1].getMessage()
    assert "stage=intent" in message
    assert "outcome=success" in message
    assert "model_id=intent-model" in message
    assert "prompt_id=intent_classifier/v1" in message
    assert "secret user" not in message


@pytest.mark.asyncio
async def test_mind_intent_bypass_and_rejected_paths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    agent = AsyncMock()
    agent.has_pending_session = AsyncMock(return_value=False)
    mind = Mind(
        language_provider=MindFakeLanguage(),
        perception=AsyncMock(),
        memory_provider=AsyncMock(),
        affect_provider=AsyncMock(),
        cognition_provider=None,
        agent=agent,
    )
    routing = RoutingContext(current_user_text="hi", recent_messages=[])
    with caplog.at_level(logging.INFO, logger="yoda.mind.mind"):
        assert await mind._classify_intent(1, routing) == "chat"
    assert any(
        "outcome=not_applicable" in r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.mind"
    )

    class _RejectingCognition:
        async def classify_intent(self, routing: RoutingContext) -> str:
            raise StructuredOutputError()

    mind.cognition_provider = _RejectingCognition()  # type: ignore[assignment]
    with caplog.at_level(logging.WARNING, logger="yoda.mind.mind"):
        assert await mind._classify_intent(1, routing) == "chat"
    assert any(
        "outcome=rejected" in r.getMessage() and "secret" not in r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.mind"
    )


@pytest.mark.asyncio
async def test_agent_selection_planning_execution_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = AgentFakeLanguage(
        [
            _select("test_skill", "Do the thing"),
            _call_tools(ToolCallRequest(tool_name="web_search", arguments={"query": "q"})),
            _finish("done"),
        ],
    )
    agent = Agent(
        language_provider=llm,  # type: ignore[arg-type]
        tools=[AskUserTool(), FakeTool()],
        skills_dir=FIXTURES_DIR,
        session_provider=AgentSessionProvider(storage_api=FakeStorageApi()),
    )
    with caplog.at_level(logging.INFO, logger="yoda.mind.agent.agent"):
        result = await agent.run(
            task="secret user task please",
            profile=UserProfile(),
            chat_id=1,
            user_id=1,
        )
    assert result.outcome is not None
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.agent.agent" and "stage=" in r.getMessage()
    ]
    joined = "\n".join(messages)
    assert "stage=selection" in joined
    assert "stage=planning" in joined
    assert "stage=execution" in joined
    assert "prompt_id=skill_selector/v1" in joined
    assert "prompt_id=skill_executor/v1" in joined
    assert "prompt_id=test_skill/v1" in joined
    assert "secret user" not in joined


@pytest.mark.asyncio
async def test_agent_selection_corrected_then_exhausted_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from yoda.mind.perception.language import StructuredOutputError

    llm = AgentFakeLanguage(
        [
            StructuredOutputError(),
            StructuredOutputError(),
        ],
    )
    agent = Agent(
        language_provider=llm,  # type: ignore[arg-type]
        tools=[AskUserTool(), FakeTool()],
        skills_dir=FIXTURES_DIR,
        session_provider=AgentSessionProvider(storage_api=FakeStorageApi()),
    )
    with caplog.at_level(logging.WARNING, logger="yoda.mind.agent.agent"):
        result = await agent.run(
            task="secret again",
            profile=UserProfile(),
            chat_id=2,
            user_id=2,
        )
    assert result.outcome is not None
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.agent.agent" and "stage=selection" in r.getMessage()
    ]
    joined = "\n".join(messages)
    assert "outcome=corrected" in joined
    assert "outcome=exhausted" in joined
    assert "secret" not in joined


@pytest.mark.asyncio
async def test_agent_execution_failure_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from yoda.mind.agent.data.agent_data import ExecutionDecision

    llm = AgentFakeLanguage(
        [
            _select("test_skill", "Do unsupported work."),
            ExecutionDecision(mode="fail", failure_reason="unsupported"),
        ],
    )
    agent = Agent(
        language_provider=llm,  # type: ignore[arg-type]
        tools=[AskUserTool(), FakeTool()],
        skills_dir=FIXTURES_DIR,
        session_provider=AgentSessionProvider(storage_api=FakeStorageApi()),
    )
    with caplog.at_level(logging.WARNING, logger="yoda.mind.agent.agent"):
        result = await agent.run(
            task="secret unsupported request",
            profile=UserProfile(),
            chat_id=3,
            user_id=3,
        )
    assert result.outcome is not None
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.agent.agent" and "stage=execution" in r.getMessage()
    ]
    assert messages
    joined = "\n".join(messages)
    assert "outcome=failed" in joined
    assert "detail=unsupported" in joined
    assert "secret" not in joined


@pytest.mark.asyncio
async def test_mind_delivery_diagnostic_success_and_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    memory = AsyncMock()
    memory.append_message = AsyncMock(return_value=(object(), []))
    memory.save_conversation = lambda conversation: None
    mind = Mind(
        language_provider=MindFakeLanguage(),
        perception=AsyncMock(),
        memory_provider=memory,
        affect_provider=AsyncMock(),
    )
    failure = OutcomeCore.failure(
        UserOperation.REQUESTED_WORK,
        SafeFailureCategory.UNSUPPORTED,
    )
    with caplog.at_level(logging.WARNING, logger="yoda.mind.mind"):
        await mind._deliver_via_core(
            chat_id=1,
            result=failure,
            system_prompt="sys",
            conversation=object(),
        )
    assert any(
        "stage=delivery" in r.getMessage() and "outcome=failed" in r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.mind"
    )
    assert all("source_text" not in r.getMessage() for r in caplog.records)

    from yoda.mind.agent.data.outcome_data import StaticMessageDelivery

    ok = StaticMessageDelivery(reminder_text="stored reminder")
    with caplog.at_level(logging.INFO, logger="yoda.mind.mind"):
        await mind._deliver_via_core(
            chat_id=1,
            result=ok,
            system_prompt="sys",
            conversation=object(),
        )
    assert any(
        "stage=delivery" in r.getMessage()
        and "outcome=success" in r.getMessage()
        and "prompt_id=grounded_delivery/v1" in r.getMessage()
        for r in caplog.records
        if r.name == "yoda.mind.mind"
    )
    assert all("stored reminder" not in r.getMessage() for r in caplog.records)
