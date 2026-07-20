import pytest

from yoda.mind.memory.data.chroma_summary_record import ChromaSummaryRecord
from yoda.mind.memory.data.summary_store_settings import EmbeddingsSettings, SummaryStoreSettings
from yoda.mind.memory.vector import VectorProvider


def _settings(tmp_path) -> SummaryStoreSettings:
    return SummaryStoreSettings(
        persist_directory=str(tmp_path / "chroma"),
        collection_prefix="chat_",
        embeddings=EmbeddingsSettings(
            model_name="openai/text-embedding-3-small",
            openrouter_api_key="sk-test",
        ),
    )


def _sample_record(summary_id: str, document: str, dim: int = 4) -> ChromaSummaryRecord:
    return ChromaSummaryRecord(
        summary_id=summary_id,
        document=document,
        embedding=[0.1] * dim,
        compressed_at=100.0,
        content_from_ts="2026-01-01T00:00:00+00:00",
        content_to_ts="2026-01-01T01:00:00+00:00",
        skills=["skill-a"],
        topics=["topic-b"],
    )


@pytest.mark.asyncio
async def test_vector_provider_upsert_round_trip(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    record = _sample_record("sum-1", "hello summary")
    await provider.persist_summaries(42, [record])

    stored = await provider.list_stored_records(42)
    assert len(stored) == 1
    assert stored[0].summary_id == "sum-1"
    assert stored[0].document == "hello summary"
    assert stored[0].embedding == pytest.approx([0.1] * 4)

    collection = provider._get_collection(42)
    raw = collection.get(ids=["sum-1"], include=["metadatas"])
    metadata = raw["metadatas"][0]
    assert metadata["compressed_at"] == 100.0
    assert metadata["content_from_ts"] == "2026-01-01T00:00:00+00:00"
    assert metadata["content_to_ts"] == "2026-01-01T01:00:00+00:00"
    assert metadata["skills"] == "skill-a"
    assert metadata["topics"] == "topic-b"


@pytest.mark.asyncio
async def test_vector_provider_collection_isolation(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    await provider.persist_summaries(1, [_sample_record("a", "chat-1")])
    await provider.persist_summaries(2, [_sample_record("b", "chat-2")])

    chat_one = await provider.list_stored_records(1)
    chat_two = await provider.list_stored_records(2)
    assert [record.summary_id for record in chat_one] == ["a"]
    assert [record.summary_id for record in chat_two] == ["b"]


@pytest.mark.asyncio
async def test_vector_provider_upsert_overwrites_same_id(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    await provider.persist_summaries(7, [_sample_record("same-id", "first")])
    await provider.persist_summaries(7, [_sample_record("same-id", "second")])

    stored = await provider.list_stored_records(7)
    assert len(stored) == 1
    assert stored[0].document == "second"


@pytest.mark.asyncio
async def test_vector_provider_delete_summary_ids(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    await provider.persist_summaries(3, [_sample_record("del-me", "x")])
    await provider.delete_summary_ids(3, ["del-me"])
    assert await provider.list_stored_records(3) == []


@pytest.mark.asyncio
async def test_vector_provider_delete_summary_ids_noop_when_empty_or_missing(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    await provider.delete_summary_ids(99, [])
    await provider.delete_summary_ids(99, ["ghost"])
    assert await provider.list_stored_records(99) == []


@pytest.mark.asyncio
async def test_vector_provider_list_stored_records_empty_when_missing(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    assert await provider.list_stored_records(99) == []


@pytest.mark.asyncio
async def test_vector_provider_encrypt_decrypt_identity(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    plaintext = "narrative text"
    assert provider.encrypt(plaintext) == plaintext
    assert provider.decrypt(plaintext) == plaintext
    await provider.persist_summaries(5, [_sample_record("enc-1", plaintext)])
    stored = await provider.list_stored_records(5)
    assert stored[0].document == plaintext


def test_vector_provider_list_chat_ids(tmp_path):
    provider = VectorProvider(_settings(tmp_path))
    assert provider.list_chat_ids() == []

    import asyncio

    asyncio.run(provider.persist_summaries(10, [_sample_record("x", "doc")]))
    asyncio.run(provider.persist_summaries(20, [_sample_record("y", "doc")]))
    assert provider.list_chat_ids() == [10, 20]
