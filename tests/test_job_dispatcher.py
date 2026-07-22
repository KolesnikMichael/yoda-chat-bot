import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from yoda.mind.job_dispatcher import JobDispatcher
from yoda.mind.agent.data.agent_data import RequestConstraints
from tests.test_agent_tools import FakeSchedulerApi, FakeStorageApi


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schedule_type",
    [None, "once", "cron"],
    ids=["legacy", "one-shot", "recurring"],
)
async def test_dispatcher_routes_message_job(schedule_type: str | None) -> None:
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    mind = MagicMock()
    mind.deliver_scheduled_reminder = AsyncMock()
    mind.execute_scheduled_task = AsyncMock()

    job = {
        "kind": "message",
        "user_id": 5,
        "message_text": "hello",
        "description": "hello",
    }
    if schedule_type is not None:
        job["type"] = schedule_type
    payload = json.dumps(job)
    await storage.hset("active_jobs:42", "job_1", payload)

    dispatcher = JobDispatcher(storage, scheduler, mind)
    await dispatcher.fire(42, "job_1")

    mind.deliver_scheduled_reminder.assert_awaited_once_with(
        chat_id=42, user_id=5, reminder_text="hello"
    )
    mind.execute_scheduled_task.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schedule_type",
    [None, "once", "cron"],
    ids=["legacy", "one-shot", "recurring"],
)
async def test_dispatcher_routes_task_job(schedule_type: str | None) -> None:
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    mind = MagicMock()
    mind.deliver_scheduled_reminder = AsyncMock()
    mind.execute_scheduled_task = AsyncMock()

    job = {
        "kind": "task",
        "user_id": 5,
        "skill_name": "search_web",
        "distilled_task": "Find news",
    }
    if schedule_type is not None:
        job["type"] = schedule_type
    payload = json.dumps(job)
    await storage.hset("active_jobs:42", "job_2", payload)

    dispatcher = JobDispatcher(storage, scheduler, mind)
    await dispatcher.fire(42, "job_2")

    mind.execute_scheduled_task.assert_awaited_once_with(
        chat_id=42,
        user_id=5,
        skill_name="search_web",
        distilled_task="Find news",
        request_constraints=RequestConstraints(),
    )


@pytest.mark.asyncio
async def test_dispatcher_routes_task_job_with_constraints():
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    mind = MagicMock()
    mind.execute_scheduled_task = AsyncMock()

    payload = json.dumps({
        "kind": "task",
        "user_id": 5,
        "skill_name": "search_web",
        "distilled_task": "Find news from Reuters only",
        "request_constraints": {
            "strict_source_domains": ["reuters.com"],
            "soft_source_domains": [],
        },
    })
    await storage.hset("active_jobs:42", "job_3", payload)

    dispatcher = JobDispatcher(storage, scheduler, mind)
    await dispatcher.fire(42, "job_3")

    kwargs = mind.execute_scheduled_task.await_args.kwargs
    assert kwargs["distilled_task"] == "Find news from Reuters only"
    assert kwargs["request_constraints"].strict_source_domains == ["reuters.com"]
    assert kwargs["request_constraints"].soft_source_domains == []


@pytest.mark.asyncio
async def test_dispatcher_missing_payload_cancels_job():
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    scheduler._live_job_ids.add("orphan")
    mind = MagicMock()

    dispatcher = JobDispatcher(storage, scheduler, mind)
    await dispatcher.fire(42, "orphan")

    assert "orphan" not in scheduler._live_job_ids


@pytest.mark.asyncio
async def test_dispatcher_task_failure_notifies():
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    mind = MagicMock()
    mind.execute_scheduled_task = AsyncMock(side_effect=RuntimeError("boom"))
    mind.notify_scheduled_failure = AsyncMock()

    payload = json.dumps({
        "kind": "task",
        "user_id": 1,
        "skill_name": "search_web",
        "distilled_task": "x",
    })
    await storage.hset("active_jobs:1", "job_t", payload)

    dispatcher = JobDispatcher(storage, scheduler, mind)
    await dispatcher.fire(1, "job_t")

    mind.notify_scheduled_failure.assert_awaited_once()
