from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from yoda.mind.agent.agent_provider import AgentProvider
from yoda.mind.agent.data.agent_data import (
    AgentContext,
    Decision,
    SkillSummary,
    ToolCallRequest,
    ToolResult,
)
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.tools.ask_user_tool import AskUserTool
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.memory.data.user_profile import UserProfile

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "skills"


class FakeStorageApi:
    def __init__(self):
        self.data = {}

    async def hget(self, key, field):
        return self.data.get(key, {}).get(field)

    async def hset(self, key, field, value):
        bucket = self.data.setdefault(key, {})
        bucket[field] = value
        return 1

    async def hdel(self, key, field):
        bucket = self.data.get(key, {})
        if field in bucket:
            del bucket[field]
            return 1
        return 0


class FakeTool(Tool):
    name = "web_search"

    class Params:
        @classmethod
        def model_json_schema(cls):
            return {"properties": {"query": {"type": "string"}}, "required": ["query"]}

    parameters_schema = Params

    def __init__(self):
        self.calls = []

    async def execute(self, call):
        self.calls.append(call)
        return ToolResult(tool_name=self.name, output="search result", success=True)


class FakeLanguageProvider:
    """Returns pre-configured Decision sequences."""

    def __init__(self, decisions: list[Decision]):
        self._decisions = list(decisions)
        self._call_index = 0

    async def parse_structured(self, messages, response_format):
        decision = self._decisions[self._call_index]
        self._call_index += 1
        return decision


def _build_provider(
    decisions: list[Decision],
    tools: list[Tool] | None = None,
) -> AgentProvider:
    if tools is None:
        tools = [AskUserTool(), FakeTool()]
    llm = FakeLanguageProvider(decisions)
    session_provider = AgentSessionProvider(storage_api=FakeStorageApi())
    return AgentProvider(
        language_provider=llm,
        tools=tools,
        skills_dir=FIXTURES_DIR,
        session_provider=session_provider,
    )


@pytest.mark.asyncio
async def test_full_flow_select_skill_and_use_tool():
    decisions = [
        Decision(selected_skill="test_skill"),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="web_search", arguments={"query": "test"}),
        ]),
        Decision(final_answer="Here is the answer"),
    ]

    provider = _build_provider(decisions)
    result = await provider.run(
        task="search for something",
        profile=UserProfile(),
        chat_id=1,
    )

    assert result.answer == "Here is the answer"
    assert "web_search" in result.tools_used


@pytest.mark.asyncio
async def test_no_matching_skill_returns_final_answer():
    decisions = [
        Decision(final_answer="I cannot help with that"),
    ]

    provider = _build_provider(decisions)
    result = await provider.run(
        task="do something impossible",
        profile=UserProfile(),
        chat_id=1,
    )

    assert result.answer == "I cannot help with that"


@pytest.mark.asyncio
async def test_suspend_on_ask_user():
    decisions = [
        Decision(selected_skill="test_skill"),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="ask_user", arguments={"question": "What timezone?"}),
        ]),
    ]

    provider = _build_provider(decisions)
    result = await provider.run(
        task="remind me about something",
        profile=UserProfile(),
        chat_id=100,
    )

    assert result.clarification == "What timezone?"
    assert result.answer is None
    assert await provider.has_pending_session(100) is True


@pytest.mark.asyncio
async def test_resume_after_suspend():
    decisions = [
        Decision(selected_skill="test_skill"),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="ask_user", arguments={"question": "What timezone?"}),
        ]),
        Decision(final_answer="Reminder set for Moscow time"),
    ]

    provider = _build_provider(decisions)

    result1 = await provider.run(
        task="remind me",
        profile=UserProfile(),
        chat_id=200,
    )
    assert result1.clarification == "What timezone?"

    result2 = await provider.resume(200, "Europe/Moscow")

    assert result2.answer == "Reminder set for Moscow time"
    assert await provider.has_pending_session(200) is False


@pytest.mark.asyncio
async def test_resume_without_session():
    provider = _build_provider([])
    result = await provider.resume(999, "some answer")

    assert result.answer == "No pending session found."
