import pytest

from yoda.mind.agent.data.agent_data import (
    AgentContext,
    SkillSpec,
    SkillSummary,
    ToolResult,
)
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.memory.data.user_profile import UserProfile


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


def _make_context() -> AgentContext:
    return AgentContext(
        task="remind me to call mom",
        profile=UserProfile(timezone="Europe/Moscow", nickname="Luke"),
        chat_id=42,
        catalog_summaries=[SkillSummary(name="schedule_message", description="Schedule")],
        active_skill=SkillSpec(
            name="schedule_message",
            description="Schedule",
            required_inputs={"text": "what"},
            tools=["schedule_message"],
            instructions="Do it",
            max_iterations=3,
        ),
        history=[ToolResult(tool_name="ask_user", output="Europe/Moscow", success=True)],
        iteration=1,
        tools_used=["ask_user"],
    )


@pytest.mark.asyncio
async def test_save_and_load_roundtrip():
    storage = FakeStorageApi()
    provider = AgentSessionProvider(storage_api=storage)

    context = _make_context()
    await provider.save(context)
    loaded = await provider.load(42)

    assert loaded is not None
    assert loaded.task == context.task
    assert loaded.chat_id == context.chat_id
    assert loaded.profile.timezone == "Europe/Moscow"
    assert loaded.profile.nickname == "Luke"
    assert loaded.active_skill.name == "schedule_message"
    assert len(loaded.history) == 1
    assert loaded.history[0].tool_name == "ask_user"
    assert loaded.iteration == 1
    assert loaded.tools_used == ["ask_user"]


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none():
    storage = FakeStorageApi()
    provider = AgentSessionProvider(storage_api=storage)

    loaded = await provider.load(999)

    assert loaded is None


@pytest.mark.asyncio
async def test_has_session():
    storage = FakeStorageApi()
    provider = AgentSessionProvider(storage_api=storage)

    assert await provider.has_session(42) is False

    await provider.save(_make_context())
    assert await provider.has_session(42) is True


@pytest.mark.asyncio
async def test_delete_removes_session():
    storage = FakeStorageApi()
    provider = AgentSessionProvider(storage_api=storage)

    await provider.save(_make_context())
    assert await provider.has_session(42) is True

    await provider.delete(42)
    assert await provider.has_session(42) is False
