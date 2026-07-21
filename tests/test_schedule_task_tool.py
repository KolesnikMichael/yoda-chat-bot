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
    assert result.terminal_facts is not None
    assert result.terminal_facts.job_kind.value == "task"
    assert result.terminal_facts.result_kind.value == "scheduled_job"
    assert result.terminal_facts.scheduled_skill_name == "search_web"
    assert result.terminal_facts.schedule
    assert "search_web" not in result.terminal_facts.summary
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timezone",
    [None, "Invalid/Zone", "+03:00"],
)
async def test_schedule_task_cron_rejects_bad_timezone_before_side_effects(
    skills_dir: Path,
    timezone: str | None,
):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )
    args = {
        "skill_name": "search_web",
        "distilled_task": "Check rates",
        "description": "rates",
        "cron": "0 9 * * *",
    }
    if timezone is not None:
        args["timezone"] = timezone
    result = await tool.execute(
        ToolCall(
            tool_name="schedule_task",
            arguments=args,
            metadata={"chat_id": 42, "profile_timezone": "Europe/Moscow"},
        )
    )
    assert result.success is False
    assert "timezone" in result.output.lower()
    assert scheduler_api.cron_scheduled == []
    assert storage_api.data == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timezone",
    [None, "Invalid/Zone", "+03:00", "UTC+03:00"],
)
async def test_schedule_task_absolute_rejects_bad_timezone_before_side_effects(
    skills_dir: Path,
    timezone: str | None,
) -> None:
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )
    args = {
        "skill_name": "search_web",
        "distilled_task": "Find weather",
        "description": "weather",
        "year": 2030,
        "month": 6,
        "day": 15,
        "hour": 9,
        "minute": 0,
    }
    if timezone is not None:
        args["timezone"] = timezone
    result = await tool.execute(
        ToolCall(
            tool_name="schedule_task",
            arguments=args,
            metadata={"chat_id": 42, "profile_timezone": "Europe/Moscow"},
        )
    )
    assert result.success is False
    assert "timezone" in result.output.lower()
    assert scheduler_api.scheduled == []
    assert scheduler_api.cron_scheduled == []
    assert storage_api.data == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "other_mode",
    [{"delay_minutes": 10}, {"cron": "0 9 * * *"}],
    ids=["relative", "cron"],
)
async def test_schedule_task_rejects_partial_absolute_fields_with_other_mode(
    skills_dir: Path,
    other_mode: dict,
) -> None:
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )
    result = await tool.execute(
        ToolCall(
            tool_name="schedule_task",
            arguments={
                "skill_name": "search_web",
                "distilled_task": "Find weather",
                "description": "weather",
                "year": 2030,
                "timezone": "Europe/Berlin",
                **other_mode,
            },
            metadata={"chat_id": 42},
        )
    )
    assert result.success is False
    assert scheduler_api.scheduled == []
    assert scheduler_api.cron_scheduled == []
    assert storage_api.data == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timezone", "profile_timezone", "expected_timezone"),
    [
        (None, "Europe/Moscow", "Europe/Moscow"),
        (None, "Invalid/Zone", "UTC"),
        ("+03:00", "Europe/Moscow", "Europe/Moscow"),
    ],
)
async def test_schedule_task_relative_uses_valid_profile_or_utc_timezone(
    skills_dir: Path,
    timezone: str | None,
    profile_timezone: str | None,
    expected_timezone: str,
) -> None:
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )
    args = {
        "skill_name": "search_web",
        "distilled_task": "Find weather",
        "description": "weather",
        "delay_minutes": 10,
    }
    if timezone is not None:
        args["timezone"] = timezone
    result = await tool.execute(
        ToolCall(
            tool_name="schedule_task",
            arguments=args,
            metadata={"chat_id": 42, "profile_timezone": profile_timezone},
        )
    )
    assert result.success is True
    stored = json.loads(list(storage_api.data["active_jobs:42"].values())[0])
    assert stored["timezone"] == expected_timezone


@pytest.mark.asyncio
async def test_schedule_task_absolute_propagates_iana_and_constraints(
    skills_dir: Path,
):
    from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleTaskTool(
        scheduler_api=scheduler_api,
        storage_api=storage_api,
        skills_dir=skills_dir,
    )
    result = await tool.execute(
        ToolCall(
            tool_name="schedule_task",
            arguments={
                "skill_name": "search_web",
                "distilled_task": "Find weather",
                "description": "weather",
                "year": 2030,
                "month": 6,
                "day": 15,
                "hour": 9,
                "minute": 0,
                "timezone": "Europe/Berlin",
                "request_constraints": {
                    "strict_source_domains": ["accuweather.com"],
                    "soft_source_domains": [],
                },
            },
            metadata={"chat_id": 42, "user_id": 7},
        )
    )
    assert result.success is True
    assert scheduler_api.scheduled
    stored = json.loads(list(storage_api.data["active_jobs:42"].values())[0])
    assert stored["timezone"] == "Europe/Berlin"
    assert stored["request_constraints"] == {
        "strict_source_domains": ["accuweather.com"],
        "soft_source_domains": [],
    }