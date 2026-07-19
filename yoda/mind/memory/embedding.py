from yoda.api.embeddings_api import EmbeddingsApi
from yoda.mind.memory.data.summary_store_settings import EmbeddingsSettings


class EmbeddingProvider:
    MODEL_DIMENSIONS: dict[str, int] = {"openai/text-embedding-3-small": 1536}

    def __init__(
        self,
        embeddings_api: EmbeddingsApi,
        settings: EmbeddingsSettings,
    ) -> None:
        if settings.model_name not in self.MODEL_DIMENSIONS:
            raise ValueError(f"Unknown embedding model: {settings.model_name}")
        self._embeddings_api = embeddings_api
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.model_name

    @property
    def vector_dimension(self) -> int:
        return self.MODEL_DIMENSIONS[self._settings.model_name]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embeddings_api.embed(self._settings.model_name, texts)

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]
