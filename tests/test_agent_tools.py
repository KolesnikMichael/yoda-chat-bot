import json

import pytest

from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.ask_user_tool import AskUserTool


@pytest.mark.asyncio
async def test_ask_user_returns_suspend():
    tool = AskUserTool()
    call = ToolCall(tool_name="ask_user", arguments={"question": "What timezone?"})

    result = await tool.execute(call)

    assert result.suspend is True
    assert result.success is True
    assert result.output == "What timezone?"
    assert result.tool_name == "ask_user"


@pytest.mark.asyncio
async def test_ask_user_describe():
    tool = AskUserTool()
    desc = tool.describe()

    assert desc["name"] == "ask_user"
    assert "question" in desc["parameters"]


class FakeSchedulerApi:
    def __init__(self):
        self.scheduled = []

    def schedule_once(self, job_id, run_date, chat_id, text):
        self.scheduled.append({
            "job_id": job_id,
            "run_date": run_date,
            "chat_id": chat_id,
            "text": text,
        })


class FakeStorageApi:
    def __init__(self):
        self.data = {}

    async def hset(self, key, field, value):
        bucket = self.data.setdefault(key, {})
        bucket[field] = value
        return 1

    async def hget(self, key, field):
        return self.data.get(key, {}).get(field)


@pytest.mark.asyncio
async def test_scheduler_tool_schedules_reminder():
    from yoda.mind.agent.tools.scheduler_tool import SchedulerTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = SchedulerTool(scheduler_api=scheduler_api, storage_api=storage_api)

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "call mom",
            "year": 2030,
            "month": 6,
            "day": 15,
            "hour": 14,
            "minute": 30,
            "timezone": "Europe/Moscow",
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert "call mom" in result.output
    assert len(scheduler_api.scheduled) == 1
    job = scheduler_api.scheduled[0]
    assert job["chat_id"] == 42
    assert job["text"] == "call mom"

    job_keys = [k for k in storage_api.data if k.startswith("active_jobs:")]
    assert len(job_keys) == 1
    stored = json.loads(list(storage_api.data[job_keys[0]].values())[0])
    assert stored["description"] == "call mom"
    assert stored["type"] == "once"


@pytest.mark.asyncio
async def test_scheduler_tool_delay_minutes():
    from yoda.mind.agent.tools.scheduler_tool import SchedulerTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = SchedulerTool(scheduler_api=scheduler_api, storage_api=storage_api)

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "wake up",
            "delay_minutes": 30,
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert "wake up" in result.output
    assert "30 minutes" in result.output
    assert len(scheduler_api.scheduled) == 1
    assert scheduler_api.scheduled[0]["chat_id"] == 42


@pytest.mark.asyncio
async def test_scheduler_tool_rejects_past_time():
    from yoda.mind.agent.tools.scheduler_tool import SchedulerTool

    tool = SchedulerTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
    )

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "too late",
            "year": 2020,
            "month": 1,
            "day": 1,
            "hour": 0,
            "minute": 0,
            "timezone": "UTC",
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "past" in result.output


@pytest.mark.asyncio
async def test_scheduler_tool_rejects_invalid_timezone():
    from yoda.mind.agent.tools.scheduler_tool import SchedulerTool

    tool = SchedulerTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
    )

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "test",
            "year": 2030,
            "month": 1,
            "day": 1,
            "hour": 12,
            "minute": 0,
            "timezone": "Invalid/Zone",
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "timezone" in result.output.lower()


@pytest.mark.asyncio
async def test_scheduler_tool_rejects_missing_chat_id():
    from yoda.mind.agent.tools.scheduler_tool import SchedulerTool

    tool = SchedulerTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
    )

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "test",
            "year": 2030,
            "month": 1,
            "day": 1,
            "hour": 12,
            "minute": 0,
            "timezone": "UTC",
        },
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "chat_id" in result.output


@pytest.mark.asyncio
async def test_scheduler_tool_rejects_invalid_date():
    from yoda.mind.agent.tools.scheduler_tool import SchedulerTool

    tool = SchedulerTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
    )

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "test",
            "year": 2030,
            "month": 13,
            "day": 1,
            "hour": 12,
            "minute": 0,
            "timezone": "UTC",
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "date" in result.output.lower() or "Invalid" in result.output


# --- UpdateProfileTool tests ---

@pytest.mark.asyncio
async def test_update_profile_saves_fields():
    from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
    from yoda.mind.memory.memory import MemoryProvider

    storage_api = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage_api)
    tool = UpdateProfileTool(memory_provider=memory)

    call = ToolCall(
        tool_name="update_profile",
        arguments={"fields": {"timezone": "Europe/Moscow", "location": "Saint Petersburg"}},
        metadata={"user_id": 123, "chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert "timezone=Europe/Moscow" in result.output
    assert "location=Saint Petersburg" in result.output

    stored = json.loads(storage_api.data["user_profiles"]["123@42"])
    assert stored["timezone"] == "Europe/Moscow"
    assert stored["location"] == "Saint Petersburg"


@pytest.mark.asyncio
async def test_update_profile_rejects_unknown_fields():
    from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
    from yoda.mind.memory.memory import MemoryProvider

    storage_api = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage_api)
    tool = UpdateProfileTool(memory_provider=memory)

    call = ToolCall(
        tool_name="update_profile",
        arguments={"fields": {"favorite_color": "blue"}},
        metadata={"user_id": 123, "chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "favorite_color" in result.output


@pytest.mark.asyncio
async def test_update_profile_rejects_missing_metadata():
    from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
    from yoda.mind.memory.memory import MemoryProvider

    storage_api = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage_api)
    tool = UpdateProfileTool(memory_provider=memory)

    call = ToolCall(
        tool_name="update_profile",
        arguments={"fields": {"timezone": "UTC"}},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "user_id" in result.output or "chat_id" in result.output
