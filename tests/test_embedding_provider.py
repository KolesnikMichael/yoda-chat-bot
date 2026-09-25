import pytest

from yoda.mind.memory.data.summary_store_settings import EmbeddingsSettings
from yoda.mind.memory.embedding import EmbeddingProvider


class FakeEmbeddingsApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    async def embed(self, model_name: str, texts: list[str]) -> list[list[float]]:
        self.calls.append((model_name, texts))
        return [[float(index)] for index, _ in enumerate(texts)]


@pytest.mark.asyncio
async def test_embedding_provider_empty_batch_skips_api():
    api = FakeEmbeddingsApi()
    provider = EmbeddingProvider(
        embeddings_api=api,
        settings=EmbeddingsSettings(
            model_name="openai/text-embedding-3-small",
        ),
    )
    result = await provider.embed_batch([])
    assert result == []
    assert api.calls == []


@pytest.mark.asyncio
async def test_embedding_provider_embed_batch_delegates():
    api = FakeEmbeddingsApi()
    provider = EmbeddingProvider(
        embeddings_api=api,
        settings=EmbeddingsSettings(
            model_name="openai/text-embedding-3-small",
        ),
    )
    vectors = await provider.embed_batch(["a", "b"])
    assert vectors == [[0.0], [1.0]]
    assert api.calls == [("openai/text-embedding-3-small", ["a", "b"])]
    assert provider.model_name == "openai/text-embedding-3-small"
    assert provider.vector_dimension == 1536


@pytest.mark.asyncio
async def test_embedding_provider_embed_single():
    api = FakeEmbeddingsApi()
    provider = EmbeddingProvider(
        embeddings_api=api,
        settings=EmbeddingsSettings(
            model_name="openai/text-embedding-3-small",
        ),
    )
    vector = await provider.embed("only")
    assert vector == [0.0]


def test_embedding_provider_unknown_model_raises():
    api = FakeEmbeddingsApi()
    with pytest.raises(ValueError, match="Unknown embedding model"):
        EmbeddingProvider(
            embeddings_api=api,
            settings=EmbeddingsSettings(
                model_name="unknown/model",
            ),
        )
