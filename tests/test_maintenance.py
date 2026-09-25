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
from yoda.mind.memory.data.summary_outbox_entry import SummaryOutboxEntry
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.memory.summarizer import SummarizerProvider
from tests.fakes import StubEmbeddingProvider, StubVectorProvider


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
    embedding_provider: StubEmbeddingProvider | None = None,
    vector_provider: StubVectorProvider | None = None,
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
        embedding_provider=embedding_provider or StubEmbeddingProvider(),
        vector_provider=vector_provider or StubVectorProvider(),
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
        with patch.object(
            maintenance,
            "reconcile_chroma_incomplete_records",
            new_callable=AsyncMock,
            return_value=0,
        ) as chroma_mock:
            await maintenance.run_initial_pass()

    reconcile_mock.assert_awaited_once_with(storage, scheduler)
    chroma_mock.assert_awaited_once()


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
async def test_flush_summary_outbox_happy_path_clears_outbox():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    memory.save_conversation_stash = AsyncMock()  # type: ignore[method-assign]
    entry = SummaryOutboxEntry(
        summary_id="sum-1",
        document="summary text",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=[],
        topics=[],
        added_at="2026-01-01T00:00:00+00:00",
    )
    conversation = Conversation(chat_id=42, pending_vectorization=[entry])
    memory.save_conversation(conversation)
    vector = StubVectorProvider()
    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        vector_provider=vector,
    )

    await maintenance.flush_summary_outbox()

    live = memory.get_conversation(42)
    assert live is not None
    assert live.pending_vectorization == []
    stored = await vector.list_stored_records(42)
    assert len(stored) == 1
    assert stored[0].summary_id == "sum-1"
    memory.save_conversation_stash.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_summary_outbox_embed_failure_retains_outbox():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    entry = SummaryOutboxEntry(
        summary_id="sum-1",
        document="summary text",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=[],
        topics=[],
        added_at="2026-01-01T00:00:00+00:00",
    )
    conversation = Conversation(chat_id=42, pending_vectorization=[entry])
    memory.save_conversation(conversation)
    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        embedding_provider=StubEmbeddingProvider(fail=True),
    )

    await maintenance.flush_summary_outbox()

    live = memory.get_conversation(42)
    assert live is not None
    assert len(live.pending_vectorization) == 1


@pytest.mark.asyncio
async def test_flush_summary_outbox_persist_failure_retains_outbox():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    entry = SummaryOutboxEntry(
        summary_id="sum-1",
        document="summary text",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=[],
        topics=[],
        added_at="2026-01-01T00:00:00+00:00",
    )
    conversation = Conversation(chat_id=42, pending_vectorization=[entry])
    memory.save_conversation(conversation)

    class FailingVectorProvider(StubVectorProvider):
        async def persist_summaries(self, chat_id: int, records: list) -> None:
            raise RuntimeError("persist failed")

    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        vector_provider=FailingVectorProvider(),
    )

    await maintenance.flush_summary_outbox()

    live = memory.get_conversation(42)
    assert live is not None
    assert len(live.pending_vectorization) == 1


@pytest.mark.asyncio
async def test_flush_idempotent_retry():
    """Persist succeeds, then failure before outbox clear; retry upserts same id once."""
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    entry = SummaryOutboxEntry(
        summary_id="sum-1",
        document="summary text",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=[],
        topics=[],
        added_at="2026-01-01T00:00:00+00:00",
    )
    conversation = Conversation(chat_id=42, pending_vectorization=[entry])
    memory.save_conversation(conversation)

    class PersistThenFailBeforeClear(StubVectorProvider):
        def __init__(self) -> None:
            super().__init__()
            self._fail_after_persist = True

        async def persist_summaries(self, chat_id: int, records: list) -> None:
            await super().persist_summaries(chat_id, records)
            if self._fail_after_persist:
                self._fail_after_persist = False
                raise RuntimeError("simulated crash after persist, before outbox clear")

    vector = PersistThenFailBeforeClear()
    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        vector_provider=vector,
    )

    await maintenance.flush_summary_outbox()
    live = memory.get_conversation(42)
    assert live is not None
    assert len(live.pending_vectorization) == 1
    assert len(await vector.list_stored_records(42)) == 1

    await maintenance.flush_summary_outbox()

    stored = await vector.list_stored_records(42)
    assert len(stored) == 1
    assert stored[0].summary_id == "sum-1"
    assert live.pending_vectorization == []
    assert len(vector.persist_calls) == 2


@pytest.mark.asyncio
async def test_reconcile_chroma_deletes_incomplete_without_outbox():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    vector = StubVectorProvider()
    from yoda.mind.memory.vector import StoredSummaryRecord

    vector.records[42] = {
        "orphan": StoredSummaryRecord(summary_id="orphan", document="", embedding=[]),
    }
    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        vector_provider=vector,
    )

    deleted = await maintenance.reconcile_chroma_incomplete_records()

    assert deleted == 1
    assert await vector.list_stored_records(42) == []


@pytest.mark.asyncio
async def test_reconcile_chroma_keeps_complete_without_outbox():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    vector = StubVectorProvider()
    from yoda.mind.memory.vector import StoredSummaryRecord

    vector.records[42] = {
        "complete": StoredSummaryRecord(
            summary_id="complete",
            document="text",
            embedding=[0.0] * 1536,
        ),
    }
    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        vector_provider=vector,
    )

    deleted = await maintenance.reconcile_chroma_incomplete_records()

    assert deleted == 0
    assert len(await vector.list_stored_records(42)) == 1


@pytest.mark.asyncio
async def test_reconcile_chroma_keeps_incomplete_with_matching_outbox():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    entry = SummaryOutboxEntry(
        summary_id="retry",
        document="doc",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=[],
        topics=[],
        added_at="2026-01-01T00:00:00+00:00",
    )
    memory.save_conversation(Conversation(chat_id=42, pending_vectorization=[entry]))
    vector = StubVectorProvider()
    from yoda.mind.memory.vector import StoredSummaryRecord

    vector.records[42] = {
        "retry": StoredSummaryRecord(summary_id="retry", document="", embedding=[]),
    }
    maintenance = make_maintenance(
        storage_api=storage,
        memory_provider=memory,
        vector_provider=vector,
    )

    deleted = await maintenance.reconcile_chroma_incomplete_records()

    assert deleted == 0
    assert len(await vector.list_stored_records(42)) == 1


@pytest.mark.asyncio
async def test_outbox_health_warning(caplog):
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    threshold = default_compression_settings().outbox_health_threshold
    entries = [
        SummaryOutboxEntry(
            summary_id=f"sum-{index}",
            document=f"doc-{index}",
            compressed_at=float(index),
            content_from_ts="from",
            content_to_ts="to",
            skills=[],
            topics=[],
            added_at="2026-01-01T00:00:00+00:00",
        )
        for index in range(threshold + 1)
    ]
    memory.save_conversation(Conversation(chat_id=42, pending_vectorization=entries))
    maintenance = make_maintenance(storage_api=storage, memory_provider=memory)

    with caplog.at_level(logging.WARNING, logger="yoda.mind.maintenance"):
        await maintenance.flush_summary_outbox()

    assert "summary outbox depth exceeded: chat_id=42" in caplog.text
    assert f"depth={threshold + 1}" in caplog.text
    assert "doc-0" not in caplog.text



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
    forbidden = ("yoda.api.mistral_api", "yoda.api.embeddings_api", "chromadb")
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
        timeout_only_compression_settings,
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
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )

    with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
        await maintenance.compress_conversations()

    assert "compression applied: chat_id=42 trigger=size" in caplog.text
    live = memory.get_conversation(42)
    assert live is not None
    assert any(message.kind == "summary" for message in live.messages)


@pytest.mark.asyncio
async def test_timeout_apply_on_predicate(caplog):
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_timeout_compressible_conversation,
        low_compression_settings,
        timeout_only_compression_settings,
    )

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "7", json.dumps({"chat_type": "private", "history": []}))
    conversation = build_timeout_compressible_conversation(chat_id=7)
    before_visible = conversation.visible_messages
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=timeout_only_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )
    quiet_seconds = 8 * 60.0
    now = conversation.last_visible_at + quiet_seconds

    with patch("yoda.mind.maintenance.time.time", return_value=now):
        with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
            await maintenance.compress_conversations()

    assert "compression trigger candidate" in caplog.text
    assert "timeout" in caplog.text
    assert "compression applied: chat_id=7 trigger=timeout" in caplog.text
    assert summarizer.calls
    live = memory.get_conversation(7)
    assert live is not None
    assert sum(1 for message in live.messages if message.kind == "summary") == 1
    assert live.visible_messages < before_visible
    assert live.last_compressed_at > 0
    from tests.test_compression_apply import assert_post_apply_invariant

    assert_post_apply_invariant(live)
    chat_raw = await storage.hget("chats", "7")
    chat_data = json.loads(chat_raw)
    assert chat_data["history"][-1]["event"] == "compression"


@pytest.mark.asyncio
async def test_both_triggers_same_tick_size_only(caplog):
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_compressible_conversation,
        low_compression_settings,
        timeout_only_compression_settings,
    )

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "8", json.dumps({"chat_type": "private"}))
    conversation = build_compressible_conversation(chat_id=8, pair_count=6)
    conversation.visible_messages = 301
    quiet_seconds = 8 * 60.0
    conversation.last_visible_at = 100.0
    conversation.last_compressed_at = 0.0
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )

    with patch("yoda.mind.maintenance.time.time", return_value=100.0 + quiet_seconds):
        with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
            await maintenance.compress_conversations()

    assert "compression applied: chat_id=8 trigger=size" in caplog.text
    assert "trigger=timeout" not in caplog.text
    assert len(summarizer.calls) == 1


@pytest.mark.asyncio
async def test_timeout_continuous_burst_no_op():
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_continuous_burst_conversation,
        low_compression_settings,
        timeout_only_compression_settings,
    )

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "7", json.dumps({"chat_type": "private"}))
    conversation = build_continuous_burst_conversation(chat_id=7, pair_count=5)
    before_visible = conversation.visible_messages
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=timeout_only_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )
    quiet_seconds = 8 * 60.0
    now = conversation.last_visible_at + quiet_seconds

    with patch("yoda.mind.maintenance.time.time", return_value=now):
        await maintenance.compress_conversations()

    live = memory.get_conversation(7)
    assert live is not None
    assert not any(message.kind == "summary" for message in live.messages)
    assert summarizer.calls == []
    assert live.visible_messages == before_visible


@pytest.mark.asyncio
async def test_timeout_quiet_gate_blocks_apply(caplog):
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_quiet_but_internal_gap_conversation,
        low_compression_settings,
        timeout_only_compression_settings,
    )

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "7", json.dumps({"chat_type": "private"}))
    conversation = build_quiet_but_internal_gap_conversation(chat_id=7)
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=timeout_only_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )
    quiet_seconds = 8 * 60.0
    now = conversation.last_visible_at + quiet_seconds - 1.0

    with patch("yoda.mind.maintenance.time.time", return_value=now):
        with caplog.at_level(logging.DEBUG, logger="yoda.mind.maintenance"):
            await maintenance.compress_conversations()

    assert "compression applied" not in caplog.text
    assert summarizer.calls == []


@pytest.mark.asyncio
async def test_cross_trigger_size_then_timeout_variant_c():
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_compressible_conversation,
        _ts,
        low_compression_settings,
        timeout_only_compression_settings,
        assert_post_apply_invariant,
    )
    from yoda.mind.memory.compression_core import CompressionCore
    from yoda.mind.memory.data.inline_summary_envelope import InlineSummaryEnvelope
    from yoda.mind.memory.data.message import Message

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "42", json.dumps({"chat_type": "private", "history": []}))
    settings = low_compression_settings()
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=settings,
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )

    tick_base = CompressionCore.parse_message_timestamp(_ts(0.0))
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    memory.save_conversation(conversation)

    with patch("yoda.mind.maintenance.time.time", return_value=tick_base + 100.0):
        await maintenance.compress_conversations()

    live = memory.get_conversation(42)
    assert live is not None
    first_summary = next(message for message in live.messages if message.kind == "summary")
    first_envelope = InlineSummaryEnvelope.from_message_text(first_summary.text)
    first_text = first_summary.text
    first_id = first_envelope.summary_id

    user_id = 1
    for index in range(3):
        pair_index = 10 + index
        tail_hour = 8.0 + index * 2.0
        live.messages.append(
            Message(
                role="user",
                kind="user",
                text=f"tail-user-{pair_index}",
                user_id=user_id,
                message_id=100 + pair_index,
                timestamp=_ts(tail_hour),
            )
        )
        live.messages.append(
            Message(
                role="assistant",
                kind="assistant",
                text=f"tail-assistant-{pair_index}",
                message_id=200 + pair_index,
                timestamp=_ts(tail_hour + 1.0),
            )
        )
    live.visible_messages = sum(
        1 for message in live.messages if message.kind in ("user", "assistant")
    )
    last_visible = next(
        message for message in reversed(live.messages) if message.kind in ("user", "assistant")
    )
    live.last_visible_at = CompressionCore.parse_message_timestamp(last_visible.timestamp)
    live.last_compressed_at = tick_base + 100.0
    quiet_seconds = 8 * 60.0
    now = live.last_visible_at + quiet_seconds
    maintenance._compression_settings = timeout_only_compression_settings()

    with patch("yoda.mind.maintenance.time.time", return_value=now):
        await maintenance.compress_conversations()

    live = memory.get_conversation(42)
    assert live is not None
    summaries = [message for message in live.messages if message.kind == "summary"]
    assert len(summaries) >= 2
    preserved = next(message for message in summaries if message.text == first_text)
    assert InlineSummaryEnvelope.from_message_text(preserved.text).summary_id == first_id
    new_summaries = [
        message for message in summaries if message.text != first_text
    ]
    assert len(new_summaries) == 1
    new_id = InlineSummaryEnvelope.from_message_text(new_summaries[0].text).summary_id
    assert new_id != first_id
    summary_indices = [
        index for index, message in enumerate(live.messages) if message.kind == "summary"
    ]
    assert summary_indices == sorted(summary_indices)
    assert_post_apply_invariant(live)


@pytest.mark.asyncio
async def test_cross_trigger_timeout_then_timeout_variant_c():
    from tests.test_compression_apply import (
        FakeSummarizerProvider,
        build_timeout_compressible_conversation,
        _ts,
        timeout_only_compression_settings,
        assert_post_apply_invariant,
    )
    from yoda.mind.memory.compression_core import CompressionCore
    from yoda.mind.memory.data.inline_summary_envelope import InlineSummaryEnvelope
    from yoda.mind.memory.data.message import Message

    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await storage.hset("chats", "7", json.dumps({"chat_type": "private", "history": []}))
    settings = timeout_only_compression_settings()
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=FakeSchedulerApi(),
        memory_provider=memory,
        compression_settings=settings,
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
        embedding_provider=StubEmbeddingProvider(),
        vector_provider=StubVectorProvider(),
    )

    conversation = build_timeout_compressible_conversation(chat_id=7)
    memory.save_conversation(conversation)
    quiet_seconds = 8 * 60.0
    tick_one_now = conversation.last_visible_at + quiet_seconds

    with patch("yoda.mind.maintenance.time.time", return_value=tick_one_now):
        await maintenance.compress_conversations()

    live = memory.get_conversation(7)
    assert live is not None
    first_summary = next(message for message in live.messages if message.kind == "summary")
    first_text = first_summary.text
    first_id = InlineSummaryEnvelope.from_message_text(first_text).summary_id
    first_compressed_at = live.last_compressed_at

    user_id = 1
    for index in range(4):
        pair_index = 10 + index
        tail_hour = 20.0 + index * 2.0
        live.messages.append(
            Message(
                role="user",
                kind="user",
                text=f"tail-user-{pair_index}",
                user_id=user_id,
                message_id=100 + pair_index,
                timestamp=_ts(tail_hour),
            )
        )
        live.messages.append(
            Message(
                role="assistant",
                kind="assistant",
                text=f"tail-assistant-{pair_index}",
                message_id=200 + pair_index,
                timestamp=_ts(tail_hour + 1.0),
            )
        )
    live.visible_messages = sum(
        1 for message in live.messages if message.kind in ("user", "assistant")
    )
    last_visible = next(
        message for message in reversed(live.messages) if message.kind in ("user", "assistant")
    )
    live.last_visible_at = CompressionCore.parse_message_timestamp(last_visible.timestamp)
    assert live.last_visible_at > first_compressed_at
    now = live.last_visible_at + quiet_seconds

    with patch("yoda.mind.maintenance.time.time", return_value=now):
        await maintenance.compress_conversations()

    live = memory.get_conversation(7)
    assert live is not None
    summaries = [message for message in live.messages if message.kind == "summary"]
    assert len(summaries) >= 2
    preserved = next(message for message in summaries if message.text == first_text)
    assert InlineSummaryEnvelope.from_message_text(preserved.text).summary_id == first_id
    new_summaries = [message for message in summaries if message.text != first_text]
    assert len(new_summaries) == 1
    new_id = InlineSummaryEnvelope.from_message_text(new_summaries[0].text).summary_id
    assert new_id != first_id
    assert_post_apply_invariant(live)


def test_make_maintenance_accepts_summarizer_provider():
    maintenance = make_maintenance()
    assert maintenance._summarizer_provider is not None
