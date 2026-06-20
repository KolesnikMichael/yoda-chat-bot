import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from yoda.mind.data.maintenance_settings import MaintenanceSettings
from yoda.mind.maintenance import RECONCILE_EVERY_N_TICKS, Maintenance, reconcile_active_jobs
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.summarizer_result import SummarizerResult
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.memory.summarizer import SummarizerProvider


class FakeStorageApi:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, str]] = {}

    async def hset(self, key: str, field: str, value: str) -> None:
        self.data.setdefault(key, {})[field] = value

    async def hget(self, key: str, field: str) -> str | None:
        return self.data.get(key, {}).get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.data.get(key, {}))

    async def hdel(self, key: str, field: str) -> None:
        bucket = self.data.get(key)
        if bucket is not None:
            bucket.pop(field, None)

    async def keys(self, pattern: str) -> list[str]:
        prefix = pattern.removesuffix("*")
        return [key for key in self.data if key.startswith(prefix)]


class FakeSchedulerApi:
    def __init__(self) -> None:
        self._live_job_ids: set[str] = set()

    def get_job_ids(self) -> set[str]:
        return set(self._live_job_ids)


def default_compression_settings() -> ChatCompressionSettings:
    settings_path = Path(__file__).resolve().parents[1] / "settings.json"
    block = json.loads(settings_path.read_text())["mind"]["memory"]["chat_compression"]
    return ChatCompressionSettings.from_dict(block)


def make_maintenance(
    *,
    storage_api: FakeStorageApi | None = None,
    scheduler_api: FakeSchedulerApi | None = None,
    memory_provider: MemoryProvider | None = None,
    tick_minutes: int = 1,
    summarizer_provider: SummarizerProvider | None = None,
) -> Maintenance:
    storage = storage_api or FakeStorageApi()
    scheduler = scheduler_api or FakeSchedulerApi()
    memory = memory_provider or MemoryProvider(storage_api=storage)
    summarizer = summarizer_provider or _StubSummarizerProvider()
    return Maintenance(
        storage_api=storage,
        scheduler_api=scheduler,
        memory_provider=memory,
        compression_settings=default_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=tick_minutes),
        summarizer_provider=summarizer,
    )


class _StubSummarizerProvider:
    async def summarise(self, chunk, participant_profiles):
        return SummarizerResult(
            summary="stub summary",
            topics=[],
            participants=[],
            skills=[],
            profile_updates={},
        )


# --- Stage 1: MaintenanceSettings ---


def test_maintenance_settings_from_dict_valid():
    settings = MaintenanceSettings.from_dict({"tick_minutes": 60})
    assert settings.tick_minutes == 60


def test_maintenance_settings_missing_tick_minutes_raises():
    with pytest.raises(ValueError, match="Missing required key: tick_minutes"):
        MaintenanceSettings.from_dict({})


def test_maintenance_settings_empty_block_raises():
    with pytest.raises(ValueError, match="Missing required key: tick_minutes"):
        MaintenanceSettings.from_dict({})


# --- Stage 2: MemoryProvider accessors ---


def test_iter_conversations_yields_saved_conversations():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    conv_a = Conversation(chat_id=1)
    conv_b = Conversation(chat_id=2)
    memory_provider.save_conversation(conv_a)
    memory_provider.save_conversation(conv_b)

    yielded = list(memory_provider.iter_conversations())

    assert len(yielded) == 2
    assert {conversation.chat_id for conversation in yielded} == {1, 2}


def test_iter_conversations_empty_cache():
    memory_provider = MemoryProvider(storage_api=FakeStorageApi())
    assert list(memory_provider.iter_conversations()) == []


@pytest.mark.asyncio
async def test_get_chat_type_returns_private_and_group():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "1", json.dumps({"chat_type": "private"}))
    await storage.hset("chats", "2", json.dumps({"chat_type": "group"}))

    assert await memory_provider.get_chat_type(1) == "private"
    assert await memory_provider.get_chat_type(2) == "group"


@pytest.mark.asyncio
async def test_get_chat_type_missing_hash_entry_raises():
    memory_provider = MemoryProvider(storage_api=FakeStorageApi())
    with pytest.raises(ValueError, match="Missing chat_type for chat_id=99"):
        await memory_provider.get_chat_type(99)


@pytest.mark.asyncio
async def test_get_chat_type_empty_chat_type_raises():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "5", json.dumps({"chat_type": ""}))

    with pytest.raises(ValueError, match="Missing chat_type for chat_id=5"):
        await memory_provider.get_chat_type(5)


# --- Stage 4: Maintenance lifecycle and dry-run ---


@pytest.mark.asyncio
async def test_run_initial_pass_calls_reconcile():
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    maintenance = make_maintenance(storage_api=storage, scheduler_api=scheduler)

    with patch(
        "yoda.mind.maintenance.reconcile_active_jobs",
        new_callable=AsyncMock,
        return_value=0,
    ) as reconcile_mock:
        await maintenance.run_initial_pass()

    reconcile_mock.assert_awaited_once_with(storage, scheduler)


@pytest.mark.asyncio
async def test_compress_conversations_dry_run_logs_size_trigger(caplog):
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    conversation = Conversation(chat_id=42, visible_messages=301)
    memory_provider.save_conversation(conversation)
    maintenance = make_maintenance(storage_api=storage, memory_provider=memory_provider)

    with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
        await maintenance.compress_conversations()

    assert "compression trigger candidate" in caplog.text
    assert "chat_id=42" in caplog.text
    assert "size" in caplog.text


@pytest.mark.asyncio
async def test_compress_conversations_dry_run_logs_timeout_trigger(caplog):
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "7", json.dumps({"chat_type": "private"}))
    quiet_seconds = 8 * 3600.0
    last_visible_at = 100.0
    conversation = Conversation(
        chat_id=7,
        visible_messages=61,
        last_visible_at=last_visible_at,
        last_compressed_at=0.0,
    )
    memory_provider.save_conversation(conversation)
    maintenance = make_maintenance(storage_api=storage, memory_provider=memory_provider)

    with patch("yoda.mind.maintenance.time.time", return_value=last_visible_at + quiet_seconds):
        with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
            await maintenance.compress_conversations()

    assert "compression trigger candidate" in caplog.text
    assert "chat_id=7" in caplog.text
    assert "timeout" in caplog.text


@pytest.mark.asyncio
async def test_compress_conversations_dry_run_logs_both_triggers(caplog):
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "8", json.dumps({"chat_type": "private"}))
    quiet_seconds = 8 * 3600.0
    last_visible_at = 100.0
    conversation = Conversation(
        chat_id=8,
        visible_messages=301,
        last_visible_at=last_visible_at,
        last_compressed_at=0.0,
    )
    memory_provider.save_conversation(conversation)
    maintenance = make_maintenance(storage_api=storage, memory_provider=memory_provider)

    with patch("yoda.mind.maintenance.time.time", return_value=last_visible_at + quiet_seconds):
        with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
            await maintenance.compress_conversations()

    assert "size" in caplog.text
    assert "timeout" in caplog.text


@pytest.mark.asyncio
async def test_compress_conversations_no_log_when_no_triggers(caplog):
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "9", json.dumps({"chat_type": "private"}))
    conversation = Conversation(chat_id=9, visible_messages=10)
    memory_provider.save_conversation(conversation)
    maintenance = make_maintenance(storage_api=storage, memory_provider=memory_provider)

    with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
        await maintenance.compress_conversations()

    assert "compression trigger candidate" not in caplog.text


@pytest.mark.asyncio
async def test_flush_summary_outbox_is_noop():
    maintenance = make_maintenance()
    await maintenance.flush_summary_outbox()


@pytest.mark.asyncio
async def test_run_subroutine_logs_warning_on_exception(caplog):
    maintenance = make_maintenance()

    async def failing() -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING, logger="yoda.mind.maintenance"):
        await maintenance._run_subroutine("test_sub", failing())

    assert "test_sub failed" in caplog.text


@pytest.mark.asyncio
async def test_tick_loop_runs_subroutines_and_reconcile_cadence():
    maintenance = make_maintenance(tick_minutes=1)
    compress_calls = 0
    outbox_calls = 0
    reconcile_calls = 0
    tick_count = 0

    async def fake_compress() -> None:
        nonlocal compress_calls
        compress_calls += 1

    async def fake_outbox() -> None:
        nonlocal outbox_calls
        outbox_calls += 1

    async def fake_reconcile(*_args, **_kwargs) -> int:
        nonlocal reconcile_calls
        reconcile_calls += 1
        return 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal tick_count
        tick_count += 1
        if tick_count >= RECONCILE_EVERY_N_TICKS:
            raise asyncio.CancelledError

    maintenance.compress_conversations = fake_compress  # type: ignore[method-assign]
    maintenance.flush_summary_outbox = fake_outbox  # type: ignore[method-assign]

    with patch("yoda.mind.maintenance.reconcile_active_jobs", side_effect=fake_reconcile):
        with patch("yoda.mind.maintenance.asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await maintenance._tick_loop()

    assert compress_calls == RECONCILE_EVERY_N_TICKS
    assert outbox_calls == RECONCILE_EVERY_N_TICKS
    assert reconcile_calls == 1


@pytest.mark.asyncio
async def test_tick_loop_subroutine_exception_does_not_stop_loop():
    maintenance = make_maintenance(tick_minutes=1)
    compress_calls = 0

    async def flaky_compress() -> None:
        nonlocal compress_calls
        compress_calls += 1
        if compress_calls == 1:
            raise RuntimeError("first tick fails")

    async def fake_sleep(_seconds: float) -> None:
        if compress_calls >= 2:
            raise asyncio.CancelledError

    maintenance.compress_conversations = flaky_compress  # type: ignore[method-assign]
    maintenance.flush_summary_outbox = AsyncMock()  # type: ignore[method-assign]

    with patch("yoda.mind.maintenance.asyncio.sleep", side_effect=fake_sleep):
        with pytest.raises(asyncio.CancelledError):
            await maintenance._tick_loop()

    assert compress_calls >= 2


@pytest.mark.asyncio
async def test_start_installs_one_task():
    maintenance = make_maintenance(tick_minutes=1)
    maintenance.start()
    assert maintenance._loop_task is not None
    assert not maintenance._loop_task.done()
    await maintenance.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task_cleanly():
    maintenance = make_maintenance(tick_minutes=60)
    maintenance.start()
    await maintenance.stop()
    assert maintenance._loop_task is not None
    assert maintenance._loop_task.done()


@pytest.mark.asyncio
async def test_stop_idempotent():
    maintenance = make_maintenance(tick_minutes=60)
    maintenance.start()
    await maintenance.stop()
    await maintenance.stop()


# --- Stage 6: FR coverage ---


def test_maintenance_does_not_import_llm_or_embedding_apis():
    import ast
    from pathlib import Path

    source = Path("yoda/mind/maintenance.py").read_text()
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = ("yoda.api.llm_api", "embedding", "chroma", "vector")
    for module in imported:
        for token in forbidden:
            assert token not in module.lower()


@pytest.mark.asyncio
async def test_reconcile_active_jobs_from_maintenance_module():
    storage = FakeStorageApi()
    scheduler = FakeSchedulerApi()
    await storage.hset("active_jobs:42", "job_live", '{"description":"live"}')
    await storage.hset("active_jobs:42", "job_stale", '{"description":"stale"}')
    scheduler._live_job_ids = {"job_live"}

    removed = await reconcile_active_jobs(storage, scheduler)

    assert removed == 1
    assert await storage.hget("active_jobs:42", "job_live") is not None
    assert await storage.hget("active_jobs:42", "job_stale") is None


@pytest.mark.asyncio
async def test_size_trigger_apply_invokes_compression(caplog):
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_compressible_conversation,
        low_compression_settings,
    )

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
        await maintenance.compress_conversations()

    assert "compression applied: chat_id=42 trigger=size" in caplog.text
    live = memory.get_conversation(42)
    assert live is not None
    assert any(message.kind == "summary" for message in live.messages)


@pytest.mark.asyncio
async def test_timeout_no_apply_without_size_trigger(caplog):
    from tests.test_compression_apply import FakeSummarizerProvider

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "7", json.dumps({"chat_type": "private"}))
    quiet_seconds = 8 * 3600.0
    last_visible_at = 100.0
    conversation = Conversation(
        chat_id=7,
        visible_messages=61,
        last_visible_at=last_visible_at,
        last_compressed_at=0.0,
    )
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=default_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    with patch("yoda.mind.maintenance.time.time", return_value=last_visible_at + quiet_seconds):
        with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
            await maintenance.compress_conversations()

    assert "compression trigger candidate" in caplog.text
    assert "timeout" in caplog.text
    assert "compression applied" not in caplog.text
    assert summarizer.calls == []


def test_make_maintenance_accepts_summarizer_provider():
    maintenance = make_maintenance()
    assert maintenance._summarizer_provider is not None
