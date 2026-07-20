import json
from pathlib import Path

import pytest

from yoda.mind.agent.data.agent_data import ToolCall
from tests.test_agent_tools import FakeSchedulerApi, FakeStorageApi


@pytest.fixture
def skills_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "yoda" / "mind" / "agent" / "skills"


@pytest.mark.asyncio
async def test_schedule_task_once(skills_dir: Path):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )

    call = ToolCall(
        tool_name="schedule_task",
        arguments={
            "skill_name": "search_web",
            "distilled_task": "Find today's weather in Moscow and summarize in Russian.",
            "description": "Daily weather check",
            "delay_minutes": 60,
        },
        metadata={"chat_id": 42, "user_id": 7},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert len(scheduler_api.scheduled) == 1
    stored = json.loads(
        list(storage_api.data["active_jobs:42"].values())[0]
    )
    assert stored["kind"] == "task"
    assert stored["skill_name"] == "search_web"
    assert stored["type"] == "once"
    assert stored["request_constraints"] == {
        "strict_source_domains": [],
        "soft_source_domains": [],
    }
    assert stored["distilled_task"] == (
        "Find today's weather in Moscow and summarize in Russian."
    )


@pytest.mark.asyncio
async def test_schedule_task_persists_request_constraints(skills_dir: Path):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )
    distilled = "  Find Saint Petersburg forecast using only accuweather.com.  "
    call = ToolCall(
        tool_name="schedule_task",
        arguments={
            "skill_name": "search_web",
            "distilled_task": distilled,
            "description": "Constrained weather",
            "delay_minutes": 30,
            "request_constraints": {
                "strict_source_domains": ["accuweather.com"],
                "soft_source_domains": ["weather.com"],
            },
        },
        metadata={"chat_id": 42, "user_id": 7},
    )
    result = await tool.execute(call)
    assert result.success is True
    stored = json.loads(list(storage_api.data["active_jobs:42"].values())[0])
    assert stored["distilled_task"] == distilled
    assert stored["request_constraints"] == {
        "strict_source_domains": ["accuweather.com"],
        "soft_source_domains": ["weather.com"],
    }


@pytest.mark.asyncio
async def test_schedule_task_rejects_unknown_skill(skills_dir: Path):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    tool = ScheduleTaskTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
        skills_dir=skills_dir,
    )

    call = ToolCall(
        tool_name="schedule_task",
        arguments={
            "skill_name": "nonexistent_skill",
            "distilled_task": "Do something",
            "description": "test",
            "delay_minutes": 10,
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)
    assert result.success is False
    assert "Unknown skill" in result.output


@pytest.mark.asyncio
async def test_schedule_task_rejects_forbidden_skill(skills_dir: Path):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    tool = ScheduleTaskTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
        skills_dir=skills_dir,
    )

    call = ToolCall(
        tool_name="schedule_task",
        arguments={
            "skill_name": "schedule_message",
            "distilled_task": "nested",
            "description": "test",
            "delay_minutes": 10,
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)
    assert result.success is False
    assert "Cannot schedule" in result.output


@pytest.mark.asyncio
async def test_schedule_task_rejects_too_frequent_cron(skills_dir: Path):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    tool = ScheduleTaskTool(
        scheduler_api=FakeSchedulerApi(),
        storage_api=FakeStorageApi(),
        skills_dir=skills_dir,
    )

    call = ToolCall(
        tool_name="schedule_task",
        arguments={
            "skill_name": "search_web",
            "distilled_task": "Check rates",
            "description": "rates",
            "cron": "* * * * *",
            "timezone": "UTC",
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)
    assert result.success is False
    assert "minutes apart" in result.output
