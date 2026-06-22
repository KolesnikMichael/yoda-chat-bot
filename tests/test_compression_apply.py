import asyncio
import datetime as dtm
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from yoda.mind.maintenance import Maintenance
from yoda.mind.memory.compression_apply_core import CompressionApplyCore
from yoda.mind.memory.compression_core import CompressionCore
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.data.compression_snapshot import CompressionSnapshot, CompressionTransformResult
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.inline_summary_envelope import InlineSummaryEnvelope
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.summarizer_result import SummarizerResult
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.memory import MemoryCore, MemoryProvider
from yoda.mind.data.maintenance_settings import MaintenanceSettings
from tests.test_memory_operation import FakeStorageApi


def low_compression_settings() -> ChatCompressionSettings:
    return ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 4,
        "min_chunk_length": 2,
        "max_summary_count": 2,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })


def timeout_only_compression_settings() -> ChatCompressionSettings:
    return ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 2,
        "max_summary_count": 2,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })


def _msg(
    kind: str,
    *,
    role: str = "system",
    text: str = "",
    user_id: int | None = None,
    message_id: int | None = None,
    timestamp: str = "",
) -> Message:
    return Message(
        role=role,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        user_id=user_id,
        message_id=message_id,
        timestamp=timestamp,
    )


def _summary_envelope(**kwargs: object) -> InlineSummaryEnvelope:
    defaults: dict[str, object] = {
        "summary_id": "s",
        "added_at": "2026-01-01T00:00:00+00:00",
        "text": "body",
        "content_from_ts": "2026-01-01T10:00:00+00:00",
        "content_to_ts": "2026-01-02T10:00:00+00:00",
        "skills": [],
        "topics": [],
    }
    defaults.update(kwargs)
    return InlineSummaryEnvelope(**defaults)  # type: ignore[arg-type]


class FakeSummarizerProvider:
    def __init__(
        self,
        *,
        result: SummarizerResult | None = None,
        fail: bool = False,
        block_event: asyncio.Event | None = None,
        release_event: asyncio.Event | None = None,
    ) -> None:
        self._result = result or SummarizerResult(
            summary="compressed narrative",
            topics=["topic-a"],
            participants=[1],
            skills=[],
            profile_updates={},
        )
        self._fail = fail
        self._block_event = block_event
        self._release_event = release_event
        self.calls: list[tuple[list[Message], dict]] = []

    async def summarise(
        self,
        chunk: list[Message],
        participant_profiles: dict[int, UserProfile],
    ) -> SummarizerResult:
        self.calls.append((chunk, participant_profiles))
        if self._block_event is not None:
            self._block_event.set()
        if self._release_event is not None:
            await self._release_event.wait()
        if self._fail:
            raise RuntimeError("summariser failed")
        return self._result


def build_compressible_conversation(
    *,
    chat_id: int = 42,
    pair_count: int = 6,
    user_id: int = 1,
    with_intro: bool = True,
) -> Conversation:
    conversation = Conversation(chat_id=chat_id, visible_messages=pair_count * 2)
    conversation.messages.append(_msg("prompt", text="system prompt"))
    if with_intro:
        conversation.messages.append(
            _msg("user_introduction", text="intro snapshot", user_id=user_id)
        )
        conversation.introduced_users.add(user_id)
    for index in range(pair_count):
        conversation.messages.append(
            _msg(
                "user",
                role="user",
                text=f"user-{index}",
                user_id=user_id,
                message_id=100 + index,
                timestamp=f"2026-01-{index + 1:02d}T10:00:00+00:00",
            )
        )
        conversation.messages.append(
            _msg(
                "assistant",
                role="assistant",
                text=f"assistant-{index}",
                message_id=200 + index,
                timestamp=f"2026-01-{index + 1:02d}T10:00:01+00:00",
            )
        )
    return conversation


def _ts(hours: float) -> str:
    base = dtm.datetime(2026, 3, 9, 12, 0, 0, tzinfo=dtm.UTC)
    return (base + dtm.timedelta(hours=hours)).isoformat()


def build_timeout_compressible_conversation(
    *,
    chat_id: int = 7,
    user_id: int = 1,
    pairs_before_gap: int = 2,
    pairs_after_gap: int = 3,
    gap_tail_start_hour: float = 8.0,
    with_intro: bool = True,
) -> Conversation:
    conversation = Conversation(chat_id=chat_id)
    conversation.messages.append(_msg("prompt", text="system prompt"))
    if with_intro:
        conversation.messages.append(
            _msg("user_introduction", text="intro snapshot", user_id=user_id)
        )
        conversation.introduced_users.add(user_id)
    hour = 0.0
    visible = 0
    for index in range(pairs_before_gap):
        conversation.messages.append(
            _msg(
                "user",
                role="user",
                text=f"before-user-{index}",
                user_id=user_id,
                message_id=100 + index,
                timestamp=_ts(hour),
            )
        )
        hour += 1.0
        conversation.messages.append(
            _msg(
                "assistant",
                role="assistant",
                text=f"before-assistant-{index}",
                message_id=200 + index,
                timestamp=_ts(hour),
            )
        )
        hour += 1.0
        visible += 2
    for index in range(pairs_after_gap):
        pair_index = pairs_before_gap + index
        tail_hour = gap_tail_start_hour + index * 2.0
        conversation.messages.append(
            _msg(
                "user",
                role="user",
                text=f"after-user-{pair_index}",
                user_id=user_id,
                message_id=100 + pair_index,
                timestamp=_ts(tail_hour),
            )
        )
        conversation.messages.append(
            _msg(
                "assistant",
                role="assistant",
                text=f"after-assistant-{pair_index}",
                message_id=200 + pair_index,
                timestamp=_ts(tail_hour + 1.0),
            )
        )
        visible += 2
    conversation.visible_messages = visible
    last_visible = next(
        message
        for message in reversed(conversation.messages)
        if message.kind in ("user", "assistant")
    )
    conversation.last_visible_at = CompressionCore.parse_message_timestamp(
        last_visible.timestamp,
    )
    conversation.last_compressed_at = 0.0
    return conversation


def _ts_seconds(offset_seconds: float) -> str:
    base = dtm.datetime(2026, 3, 9, 12, 0, 0, tzinfo=dtm.UTC)
    return (base + dtm.timedelta(seconds=offset_seconds)).isoformat()


def build_continuous_burst_conversation(
    *,
    chat_id: int = 7,
    user_id: int = 1,
    pair_count: int = 5,
    with_intro: bool = True,
) -> Conversation:
    conversation = Conversation(chat_id=chat_id)
    conversation.messages.append(_msg("prompt", text="system prompt"))
    if with_intro:
        conversation.messages.append(
            _msg("user_introduction", text="intro snapshot", user_id=user_id)
        )
        conversation.introduced_users.add(user_id)
    visible = 0
    for index in range(pair_count):
        base_seconds = float(index * 30)
        conversation.messages.append(
            _msg(
                "user",
                role="user",
                text=f"burst-user-{index}",
                user_id=user_id,
                message_id=100 + index,
                timestamp=_ts_seconds(base_seconds),
            )
        )
        conversation.messages.append(
            _msg(
                "assistant",
                role="assistant",
                text=f"burst-assistant-{index}",
                message_id=200 + index,
                timestamp=_ts_seconds(base_seconds + 10.0),
            )
        )
        visible += 2
    conversation.visible_messages = visible
    last_visible = conversation.messages[-1]
    conversation.last_visible_at = CompressionCore.parse_message_timestamp(
        last_visible.timestamp,
    )
    conversation.last_compressed_at = 0.0
    return conversation


def build_quiet_but_internal_gap_conversation(
    *,
    chat_id: int = 7,
    user_id: int = 1,
) -> Conversation:
    conversation = build_timeout_compressible_conversation(
        chat_id=chat_id,
        user_id=user_id,
    )
    conversation.last_visible_at = CompressionCore.parse_message_timestamp(
        _ts(10.0),
    )
    return conversation


# --- Stage 1: InlineSummaryEnvelope ---


def test_inline_summary_envelope_round_trip():
    envelope = _summary_envelope(
        summary_id="abc123",
        added_at="2026-06-18T12:00:00+00:00",
        text="summary body",
        skills=["web_search"],
        topics=["weather"],
    )
    restored = InlineSummaryEnvelope.from_message_text(envelope.to_message_text())
    assert restored == envelope
    wire = json.loads(envelope.to_message_text())
    assert wire["v"] == 1


def test_inline_summary_envelope_to_llm_content_includes_presentation_header():
    envelope = _summary_envelope(
        content_from_ts="2026-01-10T08:00:00+00:00",
        content_to_ts="2026-01-20T18:00:00+00:00",
        text="narrative body",
    )
    assert envelope.to_llm_content() == (
        "[Summary · 2026-01-10 — 2026-01-20]\n"
        "narrative body"
    )


def test_summary_message_to_llm_dict_uses_presentation_content():
    message = _msg(
        "summary",
        text=_summary_envelope(
            content_from_ts="2026-01-10T08:00:00+00:00",
            content_to_ts="2026-01-20T18:00:00+00:00",
            text="narrative",
        ).to_message_text(),
    )
    assert message.to_llm_dict()["content"].startswith("[Summary · 2026-01-10 — 2026-01-20]\n")
    assert message.to_llm_dict()["content"].endswith("narrative")


def test_inline_summary_envelope_to_outbox_entry():
    envelope = _summary_envelope(
        summary_id="sid",
        skills=["search_web"],
        topics=["topic-a"],
    )
    entry = envelope.to_outbox_entry(compressed_at=100.0)
    assert entry.summary_id == "sid"
    assert entry.document == "body"
    assert entry.compressed_at == 100.0
    assert entry.skills == ["search_web"]
    assert entry.topics == ["topic-a"]
    assert entry.content_from_ts == envelope.content_from_ts
    assert entry.content_to_ts == envelope.content_to_ts


def test_inline_summary_envelope_invalid_json_raises():
    with pytest.raises(ValueError, match="Invalid inline summary JSON"):
        InlineSummaryEnvelope.from_message_text("not json")


def test_inline_summary_envelope_invalid_version_raises():
    with pytest.raises(ValueError, match="Invalid inline summary envelope version"):
        InlineSummaryEnvelope.from_message_text(json.dumps({"v": 3, "summary_id": "s", "added_at": "t", "text": "x"}))


def test_inline_summary_envelope_v1_optional_metadata_defaults():
    raw = json.dumps({"v": 1, "summary_id": "s", "added_at": "t", "text": "body"})
    envelope = InlineSummaryEnvelope.from_message_text(raw)
    assert envelope.summary_id == "s"
    assert envelope.content_from_ts == ""
    assert envelope.skills == []


def test_inline_summary_envelope_missing_required_field_raises():
    with pytest.raises(ValueError, match="Invalid inline summary envelope fields"):
        InlineSummaryEnvelope.from_message_text(
            json.dumps({"v": 1, "summary_id": "s", "added_at": "t"}),
        )


# --- Stage 1: CompressionSnapshot DTOs ---


def test_compression_snapshot_fields():
    conversation = Conversation(chat_id=1)
    snapshot = CompressionSnapshot(n_old=3, copy=conversation, snapshot_ts=123.456)
    assert snapshot.n_old == 3
    assert snapshot.copy.chat_id == 1
    assert snapshot.snapshot_ts == 123.456


def test_compression_transform_result_fields():
    conversation = Conversation(chat_id=1)
    result = CompressionTransformResult(
        copy=conversation,
        removed_users={1},
        audit_entry={"event": "compression"},
        chunk_visible_count=5,
    )
    assert result.removed_users == {1}
    assert result.chunk_visible_count == 5


# --- Stage 2: chunk helpers ---


def test_slice_compressible_skips_prompt_and_head_summaries():
    messages = [
        _msg("prompt", text="p"),
        _msg("summary", text=_summary_envelope(summary_id="s1", text="old").to_message_text()),
        _msg("user", role="user", user_id=1, text="u"),
        _msg("assistant", role="assistant", text="a"),
    ]
    start, end, chunk = CompressionApplyCore.slice_compressible_chunk(messages, split=3)
    assert start == 2
    assert end == 3
    assert len(chunk) == 1
    assert chunk[0].kind == "user"


def test_chunk_boundary_message_id_uses_message_id_or_negative_index():
    messages = [_msg("user", role="user", message_id=42), _msg("user", role="user")]
    assert CompressionApplyCore.chunk_boundary_message_id(messages, 0) == 42
    assert CompressionApplyCore.chunk_boundary_message_id(messages, 1) == -1


def test_compute_summary_id_is_deterministic():
    first = CompressionApplyCore.compute_summary_id(1, 100.0, 10, 20)
    second = CompressionApplyCore.compute_summary_id(1, 100.0, 10, 20)
    third = CompressionApplyCore.compute_summary_id(1, 100.0, 10, 21)
    assert first == second
    assert first != third
    assert len(first) == 64


def test_visible_count_counts_user_and_assistant_only():
    messages = [
        _msg("prompt"),
        _msg("user", role="user"),
        _msg("assistant", role="assistant"),
        _msg("summary"),
    ]
    assert CompressionApplyCore.visible_count(messages) == 2


def test_strip_user_introductions_removes_markers_and_collects_users():
    chunk = [
        _msg("user_introduction", user_id=1, text="intro"),
        _msg("user", role="user", user_id=1, text="hello"),
    ]
    stripped, removed = CompressionApplyCore.strip_user_introductions(chunk)
    assert removed == {1}
    assert all(message.kind != "user_introduction" for message in stripped)
    CompressionApplyCore.assert_removed_users_invariant(stripped, removed)


def test_replace_chunk_with_summary_inserts_summary_message():
    copy = Conversation(chat_id=1)
    copy.messages = [
        _msg("prompt", text="p"),
        _msg("user", role="user", user_id=1, text="u"),
        _msg("assistant", role="assistant", text="a"),
        _msg("user", role="user", user_id=1, text="tail"),
    ]
    envelope = _summary_envelope(summary_id="sid", text="summary text")
    CompressionApplyCore.replace_chunk_with_summary(copy, 1, 3, envelope)
    assert copy.messages[1].kind == "summary"
    assert copy.messages[2].kind == "user"
    assert InlineSummaryEnvelope.from_message_text(copy.messages[1].text).text == "summary text"


def test_evict_summaries_fifo_pushes_outbox_and_audit():
    copy = Conversation(chat_id=1)
    old = _summary_envelope(
        summary_id="old-id",
        added_at="2026-01-01T00:00:00+00:00",
        text="old summary",
        skills=["web_search"],
        topics=["weather"],
    )
    copy.messages = [
        _msg("prompt", text="p"),
        _msg("summary", text=old.to_message_text()),
        _msg("summary", text=_summary_envelope(summary_id="new-id", text="new").to_message_text()),
    ]
    entries, evicted = CompressionApplyCore.evict_summaries_fifo(
        copy, max_summary_count=1, snapshot_ts=100.0, summaries_added=1,
    )
    assert len(entries) == 1
    assert entries[0].summary_id == "old-id"
    assert entries[0].document == "old summary"
    assert entries[0].skills == ["web_search"]
    assert entries[0].topics == ["weather"]
    assert entries[0].compressed_at == 100.0
    assert evicted == [{"summary_id": "old-id", "added_at": "2026-01-01T00:00:00+00:00"}]
    assert sum(1 for message in copy.messages if message.kind == "summary") == 1


def test_evict_summaries_fifo_no_op_when_under_cap():
    copy = Conversation(chat_id=1)
    copy.messages = [
        _msg("prompt"),
        _msg("summary", text=_summary_envelope().to_message_text()),
    ]
    entries, evicted = CompressionApplyCore.evict_summaries_fifo(
        copy, max_summary_count=2, snapshot_ts=1.0, summaries_added=1,
    )
    assert entries == []
    assert evicted == []


def test_build_compression_audit_entry_shape():
    entry = CompressionApplyCore.build_compression_audit_entry(
        100.0,
        "summary-id",
        5,
        "2026-01-01T00:00:00+00:00",
        "2026-01-02T00:00:00+00:00",
        [{"summary_id": "e1", "added_at": "2026-01-01T00:00:00+00:00"}],
    )
    assert entry["event"] == "compression"
    assert entry["added"]["summary_id"] == "summary-id"
    assert entry["added"]["visible_count"] == 5
    assert entry["evicted"][0]["summary_id"] == "e1"


def test_apply_derived_fields_updates_counters():
    copy = Conversation(chat_id=1, visible_messages=10)
    CompressionApplyCore.apply_derived_fields(copy, 99.5, 4)
    assert copy.visible_messages == 6
    assert copy.last_compressed_at == 99.5


# --- Stage 3: introduction refresh and reconcile ---


def test_refresh_removed_users_inserts_intro_when_tail_user_exists():
    copy = Conversation(chat_id=1, introduced_users={1})
    copy.messages = [
        _msg("prompt"),
        _msg("summary", text=_summary_envelope().to_message_text()),
        _msg("user", role="user", user_id=1, text="after summary"),
    ]
    CompressionApplyCore.refresh_removed_users_on_copy(
        copy,
        summary_insert_index=1,
        removed_users={1},
        intro_text_for_user_id=lambda uid: f"intro-{uid}",
    )
    assert copy.messages[2].kind == "user_introduction"
    assert copy.messages[2].text == "intro-1"
    assert 1 in copy.introduced_users


def test_refresh_removed_users_discards_when_no_tail_user():
    copy = Conversation(chat_id=1, introduced_users={1})
    copy.messages = [
        _msg("prompt"),
        _msg("summary", text=_summary_envelope().to_message_text()),
    ]
    CompressionApplyCore.refresh_removed_users_on_copy(
        copy,
        summary_insert_index=1,
        removed_users={1},
        intro_text_for_user_id=lambda uid: "intro",
    )
    assert 1 not in copy.introduced_users


def test_reconcile_arrivals_case_d_inserts_intro_for_removed_user():
    live = Conversation(chat_id=1, introduced_users=set())
    live.messages = [
        _msg("prompt"),
        _msg("summary", text=_summary_envelope().to_message_text()),
        _msg("user", role="user", user_id=7, text="arrived during llm"),
    ]
    CompressionApplyCore.reconcile_arrivals_introductions(
        live,
        copy_end_index=2,
        removed_users={7},
        intro_text_for_user_id=lambda uid: f"fresh-{uid}",
    )
    assert live.messages[2].kind == "user_introduction"
    assert live.messages[2].text == "fresh-7"
    assert 7 in live.introduced_users


def test_reconcile_arrivals_case_b_does_not_duplicate_intro():
    live = Conversation(chat_id=1, introduced_users={7})
    live.messages = [
        _msg("prompt"),
        _msg("user", role="user", user_id=7, text="already introduced"),
    ]
    before = len(live.messages)
    CompressionApplyCore.reconcile_arrivals_introductions(
        live,
        copy_end_index=1,
        removed_users={7},
        intro_text_for_user_id=lambda uid: "should-not-insert",
    )
    assert len(live.messages) == before
    assert sum(1 for message in live.messages if message.kind == "user_introduction") == 0


# --- Stage 5: size trigger orchestration ---


@pytest.mark.asyncio
async def test_run_compression_apply_size_happy_path():
    storage = FakeStorageApi()
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    memory = MemoryProvider(storage_api=storage)
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    before_visible = conversation.visible_messages
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    await maintenance._run_compression_apply(conversation, "size", "private")

    live = memory.get_conversation(42)
    assert live is not None
    assert any(message.kind == "summary" for message in live.messages)
    assert live.last_compressed_at > 0
    assert live.visible_messages < before_visible
    assert summarizer.calls


@pytest.mark.asyncio
async def test_run_size_trigger_compression_happy_path():
    storage = FakeStorageApi()
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    memory = MemoryProvider(storage_api=storage)
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    before_visible = conversation.visible_messages
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    await maintenance._run_compression_apply(conversation, "size", "private")

    live = memory.get_conversation(42)
    assert live is not None
    assert any(message.kind == "summary" for message in live.messages)
    assert live.last_compressed_at > 0
    assert live.visible_messages < before_visible
    assert summarizer.calls


@pytest.mark.asyncio
async def test_summariser_failure_noop_leaves_state_unchanged():
    storage = FakeStorageApi()
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    memory = MemoryProvider(storage_api=storage)
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    before_messages = [message for message in conversation.messages]
    memory.save_conversation(conversation)
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=FakeSummarizerProvider(fail=True),
    )

    await maintenance._run_compression_apply(conversation, "size", "private")

    live = memory.get_conversation(42)
    assert live is not None
    assert [message.kind for message in live.messages] == [message.kind for message in before_messages]
    assert live.last_compressed_at == 0.0


@pytest.mark.asyncio
async def test_window_abort_when_no_split():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    conversation = Conversation(chat_id=1, visible_messages=1)
    conversation.messages = [_msg("prompt"), _msg("user", role="user", user_id=1, text="only")]
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider()
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    await maintenance._run_compression_apply(conversation, "size", "private")

    assert summarizer.calls == []


@pytest.mark.asyncio
async def test_profile_delta_reflected_in_refreshed_introduction():
    storage = FakeStorageApi()
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    await storage.hset(
        "user_profiles",
        "1@42",
        json.dumps({"preferred_name": "OldName", "schema_version": 2}),
    )
    memory = MemoryProvider(storage_api=storage)
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    memory.save_conversation(conversation)
    summarizer = FakeSummarizerProvider(
        result=SummarizerResult(
            summary="compressed",
            topics=[],
            participants=[1],
            skills=[],
            profile_updates={1: {"preferred_name": "NewName"}},
        )
    )
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    await maintenance._run_compression_apply(conversation, "size", "private")

    live = memory.get_conversation(42)
    assert live is not None
    intro_messages = [message for message in live.messages if message.kind == "user_introduction"]
    assert any("Preferred name: NewName" in message.text for message in intro_messages)


@pytest.mark.asyncio
async def test_concurrent_ingest_during_blocked_summariser():
    storage = FakeStorageApi()
    await storage.hset("chats", "42", json.dumps({"chat_type": "private"}))
    memory = MemoryProvider(storage_api=storage)
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    memory.save_conversation(conversation)
    entered = asyncio.Event()
    release = asyncio.Event()
    summarizer = FakeSummarizerProvider(block_event=entered, release_event=release)
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=low_compression_settings(),
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=summarizer,
    )

    compress_task = asyncio.create_task(
        maintenance._run_compression_apply(conversation, "size", "private")
    )
    await entered.wait()
    assert await memory.take_compression_snapshot(42) is not None
    await memory.append_message(
        conversation=memory.get_conversation(42),
        chat_id=42,
        kind="user",
        role="user",
        line="arrived during compression",
        user_id=1,
        message_id=999,
        timestamp="2026-06-18T12:00:00+00:00",
    )
    release.set()
    await compress_task

    live = memory.get_conversation(42)
    assert live is not None
    assert live.messages[-1].text == "arrived during compression"
    assert any(message.kind == "summary" for message in live.messages)
    assert_post_apply_invariant(live)


def assert_post_apply_invariant(conversation: Conversation) -> None:
    last_summary_index = max(
        (index for index, message in enumerate(conversation.messages) if message.kind == "summary"),
        default=-1,
    )
    tail_start = last_summary_index + 1
    seen: set[int] = set()
    for index in range(tail_start, len(conversation.messages)):
        message = conversation.messages[index]
        if message.kind != "user" or message.user_id is None or message.user_id in seen:
            continue
        user_id = message.user_id
        seen.add(user_id)
        assert user_id in conversation.introduced_users
        if index > tail_start:
            prev = conversation.messages[index - 1]
            assert prev.kind == "user_introduction" and prev.user_id == user_id


@pytest.mark.asyncio
async def test_max_summary_count_eviction_records_history_and_outbox():
    storage = FakeStorageApi()
    await storage.hset("chats", "42", json.dumps({"chat_type": "private", "history": []}))
    memory = MemoryProvider(storage_api=storage)
    conversation = build_compressible_conversation(chat_id=42, pair_count=6)
    old = _summary_envelope(
        summary_id="old-summary",
        added_at="2026-01-01T00:00:00+00:00",
        text="old body",
    )
    conversation.messages.insert(1, _msg("summary", text=old.to_message_text()))
    settings = ChatCompressionSettings.from_dict({
        **{
            "size_trigger_threshold": 4,
            "min_chunk_length": 2,
            "max_summary_count": 1,
            "gap_to_trigger_ratio": 0.5,
            "quiet_runs_before_compression": {"private": 8, "group": 8},
            "outbox_health_threshold": 10,
        }
    })
    memory.save_conversation(conversation)
    maintenance = Maintenance(
        storage_api=storage,
        scheduler_api=AsyncMock(),
        memory_provider=memory,
        compression_settings=settings,
        maintenance_settings=MaintenanceSettings(tick_minutes=1),
        summarizer_provider=FakeSummarizerProvider(),
    )

    await maintenance._run_compression_apply(conversation, "size", "private")

    live = memory.get_conversation(42)
    assert live is not None
    assert len(live.pending_vectorization) == 1
    assert live.pending_vectorization[0].summary_id == "old-summary"
    chat_raw = await storage.hget("chats", "42")
    chat_data = json.loads(chat_raw)
    assert chat_data["history"][-1]["event"] == "compression"
    assert chat_data["history"][-1]["evicted"][0]["summary_id"] == "old-summary"
