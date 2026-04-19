from pathlib import Path

import pytest

from yoda.mind.agent.agent_provider import AgentProvider
from yoda.mind.agent.data.agent_data import (
    Decision,
    ToolCallRequest,
    ToolResult,
)
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.tools.ask_user_tool import AskUserTool
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.memory.data.routing_context import RoutingContext
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
        self.messages_log: list[list[dict]] = []

    async def parse_structured(self, messages, response_format):
        self.messages_log.append(list(messages))
        decision = self._decisions[self._call_index]
        self._call_index += 1
        return decision


def _build_provider(
    decisions: list[Decision],
    tools: list[Tool] | None = None,
) -> tuple[AgentProvider, FakeLanguageProvider]:
    if tools is None:
        tools = [AskUserTool(), FakeTool()]
    llm = FakeLanguageProvider(decisions)
    session_provider = AgentSessionProvider(storage_api=FakeStorageApi())
    provider = AgentProvider(
        language_provider=llm,
        tools=tools,
        skills_dir=FIXTURES_DIR,
        session_provider=session_provider,
    )
    return provider, llm


@pytest.mark.asyncio
async def test_full_flow_select_skill_and_use_tool():
    decisions = [
        Decision(
            selected_skill="test_skill",
            distilled_task="Search the web for something relevant.",
        ),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="web_search", arguments={"query": "test"}),
        ]),
        Decision(final_answer="Here is the answer"),
    ]

    provider, llm = _build_provider(decisions)
    result = await provider.run(
        task="search for something",
        profile=UserProfile(),
        chat_id=1,
    )

    assert result.answer == "Here is the answer"
    assert "web_search" in result.tools_used
    assert len(llm.messages_log) == 3


@pytest.mark.asyncio
async def test_llm_context_static_system_and_tools_in_activation():
    """Phase 1: system prompt has no tool catalog; Phase 2: tools in activation user message."""
    decisions = [
        Decision(
            selected_skill="test_skill",
            distilled_task="Do the distilled task.",
        ),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="web_search", arguments={"query": "q"}),
        ]),
        Decision(final_answer="done"),
    ]
    provider, llm = _build_provider(decisions)
    await provider.run(task="t", profile=UserProfile(), chat_id=7)

    phase1 = llm.messages_log[0]
    assert phase1[0]["role"] == "system"
    assert "executor agent" in phase1[0]["content"]
    assert "Available tools:" not in phase1[0]["content"]
    assert phase1[-1]["role"] == "system"
    assert "Current UTC time:" in phase1[-1]["content"]

    phase2 = llm.messages_log[1]
    joined = "\n".join(
        m.get("content", "") for m in phase2 if isinstance(m.get("content"), str))
    assert "Recent conversation (newest last):" not in joined
    assert "Select the best skill" not in joined
    task_user = phase2[1]
    assert task_user["role"] == "user"
    assert "Task:" in task_user["content"]
    assert "Do the distilled task." in task_user["content"]
    activation = next(
        m for m in phase2 if m["role"] == "user" and "activated" in m["content"])
    assert "Available tools:" in activation["content"]
    assert "web_search" in activation["content"]


@pytest.mark.asyncio
async def test_selection_includes_recent_when_routing_provided():
    decisions = [
        Decision(final_answer="cannot"),
    ]
    provider, llm = _build_provider(decisions)
    routing = RoutingContext(
        current_user_text="make it 6pm",
        recent_messages=[{"role": "user", "content": "remind at 5"}],
    )
    await provider.run(
        task="make it 6pm",
        profile=UserProfile(),
        chat_id=99,
        routing=routing,
    )
    phase1 = llm.messages_log[0]
    selection = phase1[1]
    assert selection["role"] == "user"
    assert "Recent conversation (newest last):" in selection["content"]
    assert "remind at 5" in selection["content"]
    assert "Task: make it 6pm" in selection["content"]


@pytest.mark.asyncio
async def test_no_matching_skill_returns_final_answer():
    decisions = [
        Decision(final_answer="I cannot help with that"),
    ]

    provider, _ = _build_provider(decisions)
    result = await provider.run(
        task="do something impossible",
        profile=UserProfile(),
        chat_id=1,
    )

    assert result.answer == "I cannot help with that"


@pytest.mark.asyncio
async def test_suspend_on_ask_user():
    decisions = [
        Decision(
            selected_skill="test_skill",
            distilled_task="Set a reminder; timezone unknown.",
        ),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="ask_user", arguments={"question": "What timezone?"}),
        ]),
    ]

    provider, _ = _build_provider(decisions)
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
        Decision(
            selected_skill="test_skill",
            distilled_task="Set a reminder.",
        ),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="ask_user", arguments={"question": "What timezone?"}),
        ]),
        Decision(final_answer="Reminder set for Moscow time"),
    ]

    provider, _ = _build_provider(decisions)

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
    provider, _ = _build_provider([])
    result = await provider.resume(999, "some answer")

    assert result.answer == "No pending session found."


@pytest.mark.asyncio
async def test_phase1_ask_user_then_skill_then_execute():
    decisions = [
        Decision(tool_calls=[
            ToolCallRequest(
                tool_name="ask_user",
                arguments={"question": "Which city?"},
            ),
        ]),
        Decision(
            selected_skill="test_skill",
            distilled_task="Search for weather in the agreed city.",
        ),
        Decision(tool_calls=[
            ToolCallRequest(tool_name="web_search", arguments={"query": "weather"}),
        ]),
        Decision(final_answer="Sunny."),
    ]
    provider, llm = _build_provider(decisions)
    r1 = await provider.run(task="weather", profile=UserProfile(), chat_id=301)
    assert r1.clarification == "Which city?"
    assert await provider.has_pending_session(301) is True

    r2 = await provider.resume(301, "Paris")
    assert r2.answer == "Sunny."
    assert await provider.has_pending_session(301) is False

    assert len(llm.messages_log) == 4
    phase2_first = "\n".join(
        str(m.get("content", "")) for m in llm.messages_log[2])
    assert "Recent conversation" not in phase2_first
    assert "Select the best skill" not in phase2_first
