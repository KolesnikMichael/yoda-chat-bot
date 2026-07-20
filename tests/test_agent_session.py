import json

import pytest

from yoda.mind.agent.data.agent_data import (
    AgentContext,
    SkillSpec,
    SkillSummary,
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
        profile=UserProfile(timezone="Europe/Moscow", preferred_name="Luke"),
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
        messages=[
            {"role": "user", "content": "Task: remind me to call mom"},
            {"role": "assistant", "content": '{"selected_skill": "schedule_message"}'},
            {"role": "user", "content": "Skill activated."},
            {"role": "assistant", "content": '{"tool_calls": []}'},
            {"role": "user", "content": "User was asked: What timezone?"},
        ],
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
    assert loaded.profile.preferred_name == "Luke"
    assert loaded.active_skill.name == "schedule_message"
    assert len(loaded.messages) == 5
    assert loaded.messages[0]["role"] == "user"
    assert loaded.messages[1]["role"] == "assistant"
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


@pytest.mark.asyncio
async def test_load_legacy_catalog_summaries_defaults_selection_fields():
    storage = FakeStorageApi()
    provider = AgentSessionProvider(storage_api=storage)
    legacy = {
        "task": "legacy task",
        "profile": {},
        "chat_id": 7,
        "user_id": 0,
        "catalog_summaries": [
            {"name": "schedule_message", "description": "Schedule", "public": True},
        ],
        "active_skill": None,
        "messages": [{"role": "user", "content": "Task: legacy"}],
        "iteration": 0,
        "tools_used": [],
    }
    await storage.hset("agent_sessions", "7", json.dumps(legacy))

    loaded = await provider.load(7)
    assert loaded is not None
    summary = loaded.catalog_summaries[0]
    assert summary.name == "schedule_message"
    assert summary.purpose == ""
    assert summary.when_to_use == []
    assert summary.do_not_use_when == []
    assert summary.selection_examples == []


@pytest.mark.asyncio
async def test_save_load_preserves_selection_contract_fields():
    storage = FakeStorageApi()
    provider = AgentSessionProvider(storage_api=storage)
    context = AgentContext(
        task="full contract",
        profile=UserProfile(),
        chat_id=8,
        catalog_summaries=[
            SkillSummary(
                name="schedule_message",
                description="Schedule",
                public=True,
                purpose="Deliver static text later.",
                when_to_use=["Known payload."],
                do_not_use_when=["Needs fresh data."],
                selection_examples=['"vitamins" -> use'],
            ),
        ],
        messages=[{"role": "system", "content": "base"}],
    )
    await provider.save(context)
    loaded = await provider.load(8)
    assert loaded is not None
    summary = loaded.catalog_summaries[0]
    assert summary.purpose == "Deliver static text later."
    assert summary.when_to_use == ["Known payload."]
    assert summary.do_not_use_when == ["Needs fresh data."]
    assert summary.selection_examples == ['"vitamins" -> use']
