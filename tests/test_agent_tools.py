import json
from pathlib import Path

import pytest

import yoda.api.scheduler_api as scheduler_module
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
        self.cron_scheduled = []
        self._live_job_ids: set[str] = set()

    def schedule_once(self, job_id, run_date, chat_id):
        self.scheduled.append({
            "job_id": job_id,
            "run_date": run_date,
            "chat_id": chat_id,
        })
        self._live_job_ids.add(job_id)

    def schedule_cron(self, job_id, cron_expr, timezone, chat_id):
        self.cron_scheduled.append({
            "job_id": job_id,
            "cron_expr": cron_expr,
            "timezone": timezone,
            "chat_id": chat_id,
        })
        self._live_job_ids.add(job_id)

    def get_job_ids(self) -> set[str]:
        return set(self._live_job_ids)

    def cancel(self, job_id: str) -> bool:
        if job_id in self._live_job_ids:
            self._live_job_ids.discard(job_id)
            return True
        return False


class FakeStorageApi:
    def __init__(self):
        self.data = {}

    async def hset(self, key, field, value):
        bucket = self.data.setdefault(key, {})
        bucket[field] = value
        return 1

    async def hget(self, key, field):
        return self.data.get(key, {}).get(field)

    async def hdel(self, key, field):
        bucket = self.data.get(key, {})
        if field in bucket:
            del bucket[field]
            return 1
        return 0

    async def keys(self, pattern):
        import fnmatch
        return [k for k in self.data if fnmatch.fnmatch(k, pattern)]

    async def hgetall(self, key):
        return dict(self.data.get(key, {}))


class SpyMemoryProvider:
    def __init__(self) -> None:
        self.forget_calls: list[int] = []

    def forget_conversation(self, chat_id: int) -> None:
        self.forget_calls.append(chat_id)


@pytest.mark.asyncio
async def test_scheduler_tool_schedules_reminder():
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleMessageTool(scheduler_api=scheduler_api, storage_api=storage_api)

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

    job_keys = [k for k in storage_api.data if k.startswith("active_jobs:")]
    assert len(job_keys) == 1
    stored = json.loads(list(storage_api.data[job_keys[0]].values())[0])
    assert stored["description"] == "call mom"
    assert stored["type"] == "once"
    assert stored["kind"] == "message"
    assert stored["message_text"] == "call mom"
    assert stored["user_id"] == 0


@pytest.mark.asyncio
async def test_scheduler_tool_delay_minutes():
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleMessageTool(scheduler_api=scheduler_api, storage_api=storage_api)

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "wake up",
            "delay_minutes": 30,
        },
        metadata={"chat_id": 42, "user_id": 777, "profile_timezone": "Europe/Moscow"},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert "wake up" in result.output
    assert "30 minutes" in result.output
    assert len(scheduler_api.scheduled) == 1
    assert scheduler_api.scheduled[0]["chat_id"] == 42

    job_keys = [k for k in storage_api.data if k.startswith("active_jobs:")]
    assert len(job_keys) == 1
    stored = json.loads(list(storage_api.data[job_keys[0]].values())[0])
    assert stored["timezone"] == "Europe/Moscow"
    assert stored["user_id"] == 777


@pytest.mark.asyncio
async def test_scheduler_tool_delay_minutes_utc_without_profile_timezone():
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleMessageTool(scheduler_api=scheduler_api, storage_api=storage_api)

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "wake up",
            "delay_minutes": 15,
        },
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is True
    job_keys = [k for k in storage_api.data if k.startswith("active_jobs:")]
    stored = json.loads(list(storage_api.data[job_keys[0]].values())[0])
    assert stored["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_scheduler_tool_rejects_past_time():
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    tool = ScheduleMessageTool(
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
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    tool = ScheduleMessageTool(
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
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    tool = ScheduleMessageTool(
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
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    tool = ScheduleMessageTool(
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


@pytest.mark.asyncio
async def test_schedule_message_cron():
    from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    tool = ScheduleMessageTool(scheduler_api=scheduler_api, storage_api=storage_api)

    call = ToolCall(
        tool_name="schedule_message",
        arguments={
            "reminder_text": "weekly vitamins",
            "cron": "0 9 * * 1",
            "timezone": "Europe/Moscow",
        },
        metadata={"chat_id": 42, "user_id": 1},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert len(scheduler_api.cron_scheduled) == 1
    assert scheduler_api.cron_scheduled[0]["cron_expr"] == "0 9 * * 1"
    stored = json.loads(
        list(storage_api.data["active_jobs:42"].values())[0]
    )
    assert stored["type"] == "cron"
    assert stored["kind"] == "message"
    assert stored["cron"] == "0 9 * * 1"


@pytest.mark.asyncio
async def test_fire_job_invokes_callback_and_cleans_up_once():
    fired = []
    cleaned = []

    async def fire(chat_id, job_id):
        fired.append((chat_id, job_id))

    async def cleanup(chat_id, job_id):
        cleaned.append((chat_id, job_id))

    scheduler_module._fire_callback = fire
    scheduler_module._cleanup_callback = cleanup

    await scheduler_module._fire_job(42, "job_1", "once")

    assert fired == [(42, "job_1")]
    assert cleaned == [(42, "job_1")]
    scheduler_module._fire_callback = None
    scheduler_module._cleanup_callback = None


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
async def test_update_profile_saves_skill_preferences():
    from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
    from yoda.mind.memory.memory import MemoryProvider

    storage_api = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage_api)
    tool = UpdateProfileTool(memory_provider=memory)

    call = ToolCall(
        tool_name="update_profile",
        arguments={
            "fields": {
                "skill_preferences": {"web_search": ["accuweather.com"]},
            },
        },
        metadata={"user_id": 123, "chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is True
    stored = json.loads(storage_api.data["user_profiles"]["123@42"])
    assert stored["skill_preferences"] == {"web_search": ["accuweather.com"]}


@pytest.mark.asyncio
async def test_update_profile_rejects_delta_keys():
    from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
    from yoda.mind.memory.memory import MemoryProvider

    storage_api = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage_api)
    tool = UpdateProfileTool(memory_provider=memory)

    call = ToolCall(
        tool_name="update_profile",
        arguments={"fields": {"interests_to_add": ["x"]}},
        metadata={"user_id": 123, "chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "interests_to_add" in result.output


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


# --- reconcile_active_jobs tests ---

@pytest.mark.asyncio
async def test_reconcile_removes_stale_keeps_live():
    from yoda.mind.maintenance import reconcile_active_jobs

    storage_api = FakeStorageApi()
    scheduler_api = FakeSchedulerApi()

    await storage_api.hset("active_jobs:42", "job_live", '{"description":"live"}')
    await storage_api.hset("active_jobs:42", "job_stale", '{"description":"stale"}')
    scheduler_api._live_job_ids = {"job_live"}

    removed = await reconcile_active_jobs(storage_api, scheduler_api)

    assert removed == 1
    assert await storage_api.hget("active_jobs:42", "job_live") is not None
    assert await storage_api.hget("active_jobs:42", "job_stale") is None


@pytest.mark.asyncio
async def test_reconcile_across_multiple_chats():
    from yoda.mind.maintenance import reconcile_active_jobs

    storage_api = FakeStorageApi()
    scheduler_api = FakeSchedulerApi()

    await storage_api.hset("active_jobs:1", "job_a", '{"description":"a"}')
    await storage_api.hset("active_jobs:2", "job_b", '{"description":"b"}')
    await storage_api.hset("active_jobs:2", "job_c", '{"description":"c"}')
    scheduler_api._live_job_ids = {"job_c"}

    removed = await reconcile_active_jobs(storage_api, scheduler_api)

    assert removed == 2
    assert await storage_api.hget("active_jobs:1", "job_a") is None
    assert await storage_api.hget("active_jobs:2", "job_b") is None
    assert await storage_api.hget("active_jobs:2", "job_c") is not None


@pytest.mark.asyncio
async def test_reconcile_no_stale_returns_zero():
    from yoda.mind.maintenance import reconcile_active_jobs

    storage_api = FakeStorageApi()
    scheduler_api = FakeSchedulerApi()

    await storage_api.hset("active_jobs:42", "job_x", '{"description":"x"}')
    scheduler_api._live_job_ids = {"job_x"}

    removed = await reconcile_active_jobs(storage_api, scheduler_api)

    assert removed == 0
    assert await storage_api.hget("active_jobs:42", "job_x") is not None


# --- ListJobsTool tests ---

@pytest.mark.asyncio
async def test_list_jobs_returns_formatted_list():
    from yoda.mind.agent.tools.list_jobs_tool import ListJobsTool

    storage_api = FakeStorageApi()
    tool = ListJobsTool(storage_api=storage_api)

    meta_a = json.dumps({
        "job_id": "reminder_42_aaa",
        "type": "once",
        "description": "call mom",
        "deliver_at_utc": "2030-06-15T11:00:00+00:00",
        "timezone": "Europe/Moscow",
    })
    meta_b = json.dumps({
        "job_id": "reminder_42_bbb",
        "type": "once",
        "description": "buy milk",
        "deliver_at_utc": "2030-07-01T09:00:00+00:00",
        "timezone": "UTC",
    })
    await storage_api.hset("active_jobs:42", "reminder_42_aaa", meta_a)
    await storage_api.hset("active_jobs:42", "reminder_42_bbb", meta_b)

    call = ToolCall(tool_name="list_jobs", arguments={}, metadata={"chat_id": 42})
    result = await tool.execute(call)

    assert result.success is True
    assert "Active jobs (2)" in result.output
    assert "reminder_42_aaa" in result.output
    assert "call mom" in result.output
    assert "reminder_42_bbb" in result.output
    assert "buy milk" in result.output
    assert "(Europe/Moscow)" not in result.output
    assert "(UTC)" not in result.output
    assert "2030-06-15 14:00" in result.output
    assert "2030-07-01 09:00" in result.output


@pytest.mark.asyncio
async def test_list_jobs_empty():
    from yoda.mind.agent.tools.list_jobs_tool import ListJobsTool

    storage_api = FakeStorageApi()
    tool = ListJobsTool(storage_api=storage_api)

    call = ToolCall(tool_name="list_jobs", arguments={}, metadata={"chat_id": 42})
    result = await tool.execute(call)

    assert result.success is True
    assert "No active jobs" in result.output


# --- CancelJobTool tests ---

@pytest.mark.asyncio
async def test_cancel_job_removes_from_both():
    from yoda.mind.agent.tools.cancel_job_tool import CancelJobTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()
    scheduler_api._live_job_ids.add("reminder_42_aaa")
    await storage_api.hset("active_jobs:42", "reminder_42_aaa", '{"description":"call mom"}')

    tool = CancelJobTool(scheduler_api=scheduler_api, storage_api=storage_api)
    call = ToolCall(
        tool_name="cancel_job",
        arguments={"job_id": "reminder_42_aaa"},
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is True
    assert "cancelled" in result.output
    assert "reminder_42_aaa" not in scheduler_api._live_job_ids
    assert await storage_api.hget("active_jobs:42", "reminder_42_aaa") is None


@pytest.mark.asyncio
async def test_cancel_job_nonexistent():
    from yoda.mind.agent.tools.cancel_job_tool import CancelJobTool

    scheduler_api = FakeSchedulerApi()
    storage_api = FakeStorageApi()

    tool = CancelJobTool(scheduler_api=scheduler_api, storage_api=storage_api)
    call = ToolCall(
        tool_name="cancel_job",
        arguments={"job_id": "nonexistent_job"},
        metadata={"chat_id": 42},
    )

    result = await tool.execute(call)

    assert result.success is False
    assert "not found" in result.output


# --- Tavily / WebSearchTool / WebExtractTool tests ---


class FakeTavilyApi:
    def __init__(self):
        self.search_response: dict | None = None
        self.extract_response: dict | None = None
        self.search_error: Exception | None = None
        self.extract_error: Exception | None = None
        self.last_search_kwargs: dict | None = None
        self.last_extract_urls: list[str] | None = None

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
    ):
        self.last_search_kwargs = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
        }
        if self.search_error:
            raise self.search_error
        return self.search_response if self.search_response is not None else {"results": []}

    async def extract(self, urls: list[str]):
        self.last_extract_urls = urls
        if self.extract_error:
            raise self.extract_error
        return self.extract_response if self.extract_response is not None else {"results": [], "failed_results": []}


@pytest.mark.asyncio
async def test_web_search_tool_success():
    from yoda.mind.agent.tools.web_search_tool import WebSearchTool

    fake = FakeTavilyApi()
    fake.search_response = {
        "results": [
            {
                "title": "Example",
                "url": "https://example.com",
                "content": "Snippet text here.",
                "score": 0.91,
            },
        ],
    }
    tool = WebSearchTool(tavily_api=fake)

    call = ToolCall(
        tool_name="web_search",
        arguments={"query": "test query", "max_results": 3},
    )
    result = await tool.execute(call)

    assert result.success is True
    assert "test query" in result.output
    assert "Example" in result.output
    assert "https://example.com" in result.output
    assert "Snippet text" in result.output
    assert fake.last_search_kwargs["query"] == "test query"
    assert fake.last_search_kwargs["max_results"] == 3


@pytest.mark.asyncio
async def test_web_search_tool_empty_results():
    from yoda.mind.agent.tools.web_search_tool import WebSearchTool

    fake = FakeTavilyApi()
    fake.search_response = {"results": []}
    tool = WebSearchTool(tavily_api=fake)

    call = ToolCall(tool_name="web_search", arguments={"query": "nothing"})
    result = await tool.execute(call)

    assert result.success is True
    assert "No results" in result.output


@pytest.mark.asyncio
async def test_web_search_tool_api_error():
    from yoda.mind.agent.tools.web_search_tool import WebSearchTool

    fake = FakeTavilyApi()
    fake.search_error = RuntimeError("network down")
    tool = WebSearchTool(tavily_api=fake)

    call = ToolCall(tool_name="web_search", arguments={"query": "x"})
    result = await tool.execute(call)

    assert result.success is False
    assert "Search failed" in result.output
    assert "network down" in result.output


@pytest.mark.asyncio
async def test_web_search_tool_invalid_params():
    from yoda.mind.agent.tools.web_search_tool import WebSearchTool

    tool = WebSearchTool(tavily_api=FakeTavilyApi())
    call = ToolCall(tool_name="web_search", arguments={})

    result = await tool.execute(call)

    assert result.success is False
    assert "Invalid parameters" in result.output


@pytest.mark.asyncio
async def test_web_extract_tool_success():
    from yoda.mind.agent.tools.web_extract_tool import WebExtractTool

    fake = FakeTavilyApi()
    fake.extract_response = {
        "results": [
            {"url": "https://a.com", "raw_content": "Hello world"},
        ],
        "failed_results": [],
    }
    tool = WebExtractTool(tavily_api=fake)

    call = ToolCall(
        tool_name="web_extract",
        arguments={"urls": ["https://a.com"]},
    )
    result = await tool.execute(call)

    assert result.success is True
    assert "https://a.com" in result.output
    assert "Hello world" in result.output
    assert fake.last_extract_urls == ["https://a.com"]


@pytest.mark.asyncio
async def test_web_extract_tool_partial_failure():
    from yoda.mind.agent.tools.web_extract_tool import WebExtractTool

    fake = FakeTavilyApi()
    fake.extract_response = {
        "results": [{"url": "https://ok.com", "raw_content": "OK"}],
        "failed_results": [{"url": "https://bad.com", "error": "timeout"}],
    }
    tool = WebExtractTool(tavily_api=fake)

    call = ToolCall(
        tool_name="web_extract",
        arguments={"urls": ["https://ok.com", "https://bad.com"]},
    )
    result = await tool.execute(call)

    assert result.success is True
    assert "OK" in result.output
    assert "Failed URLs" in result.output
    assert "bad.com" in result.output
    assert "timeout" in result.output


@pytest.mark.asyncio
async def test_web_extract_tool_truncates_long_content():
    from yoda.mind.agent.tools.web_extract_tool import WebExtractTool

    long_text = "x" * 3000
    fake = FakeTavilyApi()
    fake.extract_response = {
        "results": [{"url": "https://long.com", "raw_content": long_text}],
        "failed_results": [],
    }
    tool = WebExtractTool(tavily_api=fake)

    call = ToolCall(
        tool_name="web_extract",
        arguments={"urls": ["https://long.com"]},
    )
    result = await tool.execute(call)

    assert result.success is True
    assert "…" in result.output
    assert len(result.output) < len(long_text) + 200


@pytest.mark.asyncio
async def test_web_extract_tool_empty_urls_invalid():
    from yoda.mind.agent.tools.web_extract_tool import WebExtractTool

    tool = WebExtractTool(tavily_api=FakeTavilyApi())
    call = ToolCall(tool_name="web_extract", arguments={"urls": []})

    result = await tool.execute(call)

    assert result.success is False
    assert "Invalid parameters" in result.output


@pytest.mark.asyncio
async def test_web_extract_tool_too_many_urls():
    from yoda.mind.agent.tools.web_extract_tool import WebExtractTool

    tool = WebExtractTool(tavily_api=FakeTavilyApi())
    urls = [f"https://x{i}.com" for i in range(21)]
    call = ToolCall(tool_name="web_extract", arguments={"urls": urls})

    result = await tool.execute(call)

    assert result.success is False
    assert "20" in result.output


@pytest.mark.asyncio
async def test_web_extract_tool_api_error():
    from yoda.mind.agent.tools.web_extract_tool import WebExtractTool

    fake = FakeTavilyApi()
    fake.extract_error = RuntimeError("extract failed")
    tool = WebExtractTool(tavily_api=fake)

    call = ToolCall(
        tool_name="web_extract",
        arguments={"urls": ["https://a.com"]},
    )
    result = await tool.execute(call)

    assert result.success is False
    assert "Extract failed" in result.output


# --- GetUserDataTool tests ---

@pytest.mark.asyncio
async def test_get_user_data_returns_all_data():
    from yoda.mind.agent.tools.get_user_data_tool import GetUserDataTool

    storage = FakeStorageApi()
    await storage.hset("users", "100", json.dumps({"username": "mike", "first_name": "Mike"}))
    await storage.hset("user_profiles", "100@42", json.dumps({"timezone": "Europe/Moscow"}))
    await storage.hset("user_profiles", "100@99", json.dumps({"timezone": "UTC"}))
    await storage.hset("user_profiles", "200@42", json.dumps({"timezone": "US/Eastern"}))
    await storage.hset("active_jobs:42", "reminder_42_abc",
                        json.dumps({"user_id": 100, "description": "call mom", "deliver_at_utc": "2030-01-01T12:00:00"}))
    await storage.hset("active_jobs:99", "reminder_99_xyz",
                        json.dumps({"user_id": 100, "description": "buy milk", "deliver_at_utc": "2030-02-01T09:00:00"}))
    await storage.hset("active_jobs:42", "reminder_42_other",
                        json.dumps({"user_id": 200, "description": "not mine", "deliver_at_utc": "2030-03-01T10:00:00"}))
    await storage.hset("chats", "100", json.dumps({"chat_type": "private", "last_active": "now"}))

    tool = GetUserDataTool(storage_api=storage)
    call = ToolCall(tool_name="get_user_data", arguments={}, metadata={"user_id": 100})
    result = await tool.execute(call)

    assert result.success is True
    assert "Private chat metadata" in result.output
    assert "mike" in result.output
    assert "100@42" in result.output or "chat 42" in result.output
    assert "100@99" in result.output or "chat 99" in result.output
    assert "200@42" not in result.output
    assert "call mom" in result.output
    assert "buy milk" in result.output
    assert "not mine" not in result.output


@pytest.mark.asyncio
async def test_get_user_data_no_data():
    from yoda.mind.agent.tools.get_user_data_tool import GetUserDataTool

    storage = FakeStorageApi()
    tool = GetUserDataTool(storage_api=storage)
    call = ToolCall(tool_name="get_user_data", arguments={}, metadata={"user_id": 999})
    result = await tool.execute(call)

    assert result.success is True
    assert "No data" in result.output


@pytest.mark.asyncio
async def test_get_user_data_missing_user_id():
    from yoda.mind.agent.tools.get_user_data_tool import GetUserDataTool

    tool = GetUserDataTool(storage_api=FakeStorageApi())
    call = ToolCall(tool_name="get_user_data", arguments={})
    result = await tool.execute(call)

    assert result.success is False
    assert "user_id" in result.output


# --- DeleteUserDataTool tests ---

@pytest.mark.asyncio
async def test_delete_user_data_removes_everything():
    from yoda.mind.agent.tools.delete_user_data_tool import DeleteUserDataTool

    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()

    await storage.hset("users", "100", json.dumps({"username": "mike"}))
    await storage.hset("users", "200", json.dumps({"username": "other"}))
    await storage.hset("user_profiles", "100@42", json.dumps({"timezone": "UTC"}))
    await storage.hset("user_profiles", "100@99", json.dumps({"timezone": "UTC"}))
    await storage.hset("user_profiles", "200@42", json.dumps({"timezone": "UTC"}))
    await storage.hset("active_jobs:42", "job_a",
                        json.dumps({"user_id": 100, "description": "a"}))
    await storage.hset("active_jobs:99", "job_b",
                        json.dumps({"user_id": 100, "description": "b"}))
    await storage.hset("active_jobs:42", "job_c",
                        json.dumps({"user_id": 200, "description": "c"}))
    await storage.hset("chats", "100", json.dumps({"chat_type": "private"}))
    scheduler._live_job_ids = {"job_a", "job_b", "job_c"}

    memory = SpyMemoryProvider()
    tool = DeleteUserDataTool(
        storage_api=storage, scheduler_api=scheduler, memory_provider=memory)
    call = ToolCall(
        tool_name="delete_user_data",
        arguments={},
        metadata={"user_id": 100, "chat_id": 42},
    )
    result = await tool.execute(call)

    assert result.success is True
    assert "user record" in result.output
    assert "2 profile(s)" in result.output
    assert "2 scheduled job(s)" in result.output
    assert "private chat metadata" in result.output
    assert memory.forget_calls == [100]

    assert await storage.hget("users", "100") is None
    assert await storage.hget("users", "200") is not None
    assert await storage.hget("user_profiles", "100@42") is None
    assert await storage.hget("user_profiles", "100@99") is None
    assert await storage.hget("user_profiles", "200@42") is not None
    assert await storage.hget("active_jobs:42", "job_a") is None
    assert await storage.hget("active_jobs:99", "job_b") is None
    assert await storage.hget("active_jobs:42", "job_c") is not None
    assert await storage.hget("chats", "100") is None
    assert "job_a" not in scheduler._live_job_ids
    assert "job_b" not in scheduler._live_job_ids
    assert "job_c" in scheduler._live_job_ids


@pytest.mark.asyncio
async def test_delete_user_data_no_data():
    from yoda.mind.agent.tools.delete_user_data_tool import DeleteUserDataTool

    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    memory = SpyMemoryProvider()
    tool = DeleteUserDataTool(
        storage_api=storage, scheduler_api=scheduler, memory_provider=memory)
    call = ToolCall(tool_name="delete_user_data", arguments={}, metadata={"user_id": 999})
    result = await tool.execute(call)

    assert result.success is True
    assert "No data" in result.output
    assert memory.forget_calls == [999]


@pytest.mark.asyncio
async def test_delete_user_data_missing_user_id():
    from yoda.mind.agent.tools.delete_user_data_tool import DeleteUserDataTool

    tool = DeleteUserDataTool(
        storage_api=FakeStorageApi(),
        scheduler_api=FakeSchedulerApi(),
        memory_provider=SpyMemoryProvider(),
    )
    call = ToolCall(tool_name="delete_user_data", arguments={})
    result = await tool.execute(call)

    assert result.success is False
    assert "user_id" in result.output


@pytest.mark.asyncio
async def test_text_to_image_success_writes_file(tmp_path, monkeypatch):
    from yoda.mind.agent.tools.text_to_image_tool import TextToImageTool
    import yoda.mind.agent.tools.text_to_image_tool as tti_mod

    monkeypatch.setattr(tti_mod, "FILE_CACHE_DIR", str(tmp_path))

    class FakePixazo:
        async def generate_image_bytes(self, prompt: str, **kwargs):
            assert "cat" in prompt.lower()
            return b"\x89PNG\r\n\x1a\nfake"

    tool = TextToImageTool(
        pixazo_api=FakePixazo(),  # type: ignore[arg-type]
    )
    call = ToolCall(
        tool_name="text_to_image",
        arguments={"english_prompt": "A small cat on a mat"},
    )
    result = await tool.execute(call)

    assert result.success is True
    p = Path(result.output)
    assert p.is_file()
    assert p.suffix == ".png"
    assert p.read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_image_to_text_success(tmp_path):
    from yoda.mind.agent.tools.image_to_text_tool import ImageToTextTool

    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nx")

    class FakeVision:
        async def image_to_description(self, path: str) -> str:
            assert Path(path).resolve() == img.resolve()
            return "  A red door  "

    tool = ImageToTextTool(vision_provider=FakeVision())  # type: ignore[arg-type]
    call = ToolCall(
        tool_name="image_to_text",
        arguments={"file_path": str(img)},
    )
    result = await tool.execute(call)
    assert result.success is True
    assert result.output == "A red door"


@pytest.mark.asyncio
async def test_image_to_text_missing_file(tmp_path):
    from yoda.mind.agent.tools.image_to_text_tool import ImageToTextTool

    class FakeVision:
        async def image_to_description(self, path: str) -> str:
            raise AssertionError("should not run")

    tool = ImageToTextTool(vision_provider=FakeVision())  # type: ignore[arg-type]
    call = ToolCall(
        tool_name="image_to_text",
        arguments={"file_path": str(tmp_path / "missing.png")},
    )
    result = await tool.execute(call)
    assert result.success is False
    assert "not found" in result.output.lower()


@pytest.mark.asyncio
async def test_image_to_text_invalid_params():
    from yoda.mind.agent.tools.image_to_text_tool import ImageToTextTool

    class FakeVision:
        async def image_to_description(self, path: str) -> str:
            raise AssertionError("should not run")

    tool = ImageToTextTool(vision_provider=FakeVision())  # type: ignore[arg-type]
    call = ToolCall(tool_name="image_to_text", arguments={})
    result = await tool.execute(call)
    assert result.success is False
    assert "Invalid parameters" in result.output


@pytest.mark.asyncio
async def test_text_to_image_invalid_params():
    from yoda.api.pixazo_api import PixazoApi
    from yoda.mind.agent.tools.text_to_image_tool import TextToImageTool

    tool = TextToImageTool(pixazo_api=PixazoApi("http://example.com", "k"))
    call = ToolCall(tool_name="text_to_image", arguments={})
    result = await tool.execute(call)
    assert result.success is False
    assert "Invalid parameters" in result.output


@pytest.mark.asyncio
async def test_send_picture_success_deletes_file(tmp_path):
    from yoda.mind.agent.tools.send_picture_tool import SendPictureTool

    img = tmp_path / "x.png"
    img.write_bytes(b"x")

    sent: list[tuple[int, str]] = []

    async def send_photo(chat_id: int, file_path: str) -> None:
        sent.append((chat_id, file_path))

    tool = SendPictureTool(send_photo=send_photo)
    call = ToolCall(
        tool_name="send_picture",
        arguments={
            "file_path": str(img),
            "summary_for_chat": "A red balloon",
        },
        metadata={"chat_id": 99},
    )
    result = await tool.execute(call)

    assert result.success is True
    assert sent[0][0] == 99
    assert "red balloon" in result.output.lower()
    assert "description:" in result.output.lower()
    assert not img.exists()


@pytest.mark.asyncio
async def test_send_picture_missing_file(tmp_path):
    from yoda.mind.agent.tools.send_picture_tool import SendPictureTool

    async def send_photo(chat_id: int, file_path: str) -> None:
        raise AssertionError("should not run")

    tool = SendPictureTool(send_photo=send_photo)
    call = ToolCall(
        tool_name="send_picture",
        arguments={
            "file_path": str(tmp_path / "nope.png"),
            "summary_for_chat": "x",
        },
        metadata={"chat_id": 1},
    )
    result = await tool.execute(call)
    assert result.success is False
    assert "not found" in result.output.lower()


@pytest.mark.asyncio
async def test_send_picture_missing_chat_id():
    from yoda.mind.agent.tools.send_picture_tool import SendPictureTool

    async def _noop(_chat_id: int, _path: str) -> None:
        pass

    tool = SendPictureTool(send_photo=_noop)
    call = ToolCall(
        tool_name="send_picture",
        arguments={"file_path": "/tmp/x", "summary_for_chat": "y"},
    )
    result = await tool.execute(call)
    assert result.success is False
    assert "chat_id" in result.output


@pytest.mark.asyncio
async def test_delete_user_data_is_terminal():
    from yoda.mind.agent.tools.delete_user_data_tool import DeleteUserDataTool

    tool = DeleteUserDataTool(
        storage_api=FakeStorageApi(),
        scheduler_api=FakeSchedulerApi(),
        memory_provider=SpyMemoryProvider(),
    )
    assert tool.terminal is True
