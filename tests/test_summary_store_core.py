import dataclasses

import pytest

from yoda.mind.memory.data.chroma_summary_record import ChromaSummaryRecord
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.summary_outbox_entry import SummaryOutboxEntry
from yoda.mind.memory.data.summary_store_settings import SummaryStoreSettings
from yoda.mind.memory.summary_store_core import SummaryStoreCore
from yoda.mind.memory.vector import StoredSummaryRecord


def test_summary_store_settings_from_dict_valid():
    settings = SummaryStoreSettings.from_dict(
        {
            "persist_directory": "data/chroma",
            "collection_prefix": "chat_",
            "embeddings": {
                "model_name": "openai/text-embedding-3-small",
                "openrouter_api_key": "sk-test",
            },
            "search": {"ignored": True},
            "document_encryption": {"ignored": True},
        }
    )
    assert settings.persist_directory == "data/chroma"
    assert settings.collection_prefix == "chat_"
    assert settings.embeddings.model_name == "openai/text-embedding-3-small"
    assert settings.embeddings.openrouter_api_key == "sk-test"


def test_summary_store_settings_missing_embeddings_key_raises():
    with pytest.raises(ValueError, match="Missing required key: embeddings.openrouter_api_key"):
        SummaryStoreSettings.from_dict(
            {
                "persist_directory": "data/chroma",
                "collection_prefix": "chat_",
                "embeddings": {"model_name": "openai/text-embedding-3-small"},
            }
        )


def test_chroma_summary_record_is_immutable():
    record = ChromaSummaryRecord(
        summary_id="abc",
        document="summary text",
        embedding=[0.1, 0.2],
        compressed_at=1.0,
        content_from_ts="2026-01-01T00:00:00+00:00",
        content_to_ts="2026-01-01T01:00:00+00:00",
        skills=["skill-a"],
        topics=["topic-b"],
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.document = "mutated"  # type: ignore[misc]


def test_summary_store_core_flatten_metadata():
    entry = SummaryOutboxEntry(
        summary_id="id-1",
        document="doc",
        compressed_at=42.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=["a", "b"],
        topics=["x"],
        added_at="2026-01-01T00:00:00+00:00",
    )
    metadata = SummaryStoreCore.flatten_metadata(entry)
    assert metadata == {
        "compressed_at": 42.0,
        "content_from_ts": "from",
        "content_to_ts": "to",
        "skills": "a,b",
        "topics": "x",
    }


def test_summary_store_core_outbox_entries_to_records():
    entry = SummaryOutboxEntry(
        summary_id="id-1",
        document="doc",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=["s"],
        topics=["t"],
        added_at="2026-01-01T00:00:00+00:00",
    )
    records = SummaryStoreCore.outbox_entries_to_records([entry], [[0.1, 0.2]])
    assert len(records) == 1
    assert records[0].summary_id == "id-1"
    assert records[0].embedding == [0.1, 0.2]


def test_summary_store_core_pending_outbox_ids():
    entry = SummaryOutboxEntry(
        summary_id="id-1",
        document="doc",
        compressed_at=1.0,
        content_from_ts="from",
        content_to_ts="to",
        skills=[],
        topics=[],
        added_at="2026-01-01T00:00:00+00:00",
    )
    conversation = Conversation(chat_id=1, pending_vectorization=[entry])
    assert SummaryStoreCore.pending_outbox_ids([conversation]) == {"id-1"}


def test_summary_store_core_is_complete_record():
    complete = StoredSummaryRecord(summary_id="a", document="text", embedding=[0.0] * 3)
    incomplete_doc = StoredSummaryRecord(summary_id="b", document="", embedding=[0.0] * 3)
    incomplete_dim = StoredSummaryRecord(summary_id="c", document="text", embedding=[0.0])
    assert SummaryStoreCore.is_complete_record(complete, expected_dimension=3)
    assert not SummaryStoreCore.is_complete_record(incomplete_doc, expected_dimension=3)
    assert not SummaryStoreCore.is_complete_record(incomplete_dim, expected_dimension=3)


def test_summary_store_core_incomplete_ids_to_delete():
    complete = StoredSummaryRecord(summary_id="keep-complete", document="x", embedding=[0.0] * 2)
    orphan = StoredSummaryRecord(summary_id="delete-me", document="", embedding=[])
    retryable = StoredSummaryRecord(summary_id="retry", document="", embedding=[])
    pending = {"retry"}
    to_delete = SummaryStoreCore.incomplete_ids_to_delete(
        [complete, orphan, retryable],
        pending,
        expected_dimension=2,
    )
    assert to_delete == ["delete-me"]
