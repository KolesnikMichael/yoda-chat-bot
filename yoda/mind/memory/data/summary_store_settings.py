from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingsSettings:
    model_name: str
    openrouter_api_key: str


@dataclass(frozen=True)
class SummaryStoreSettings:
    persist_directory: str
    collection_prefix: str
    embeddings: EmbeddingsSettings

    @classmethod
    def from_dict(cls, block: dict) -> "SummaryStoreSettings":
        required_keys = ("persist_directory", "collection_prefix", "embeddings")
        for key in required_keys:
            if key not in block:
                raise ValueError(f"Missing required key: {key}")

        embeddings_block = block["embeddings"]
        for key in ("model_name", "openrouter_api_key"):
            if key not in embeddings_block:
                raise ValueError(f"Missing required key: embeddings.{key}")

        return cls(
            persist_directory=str(block["persist_directory"]),
            collection_prefix=str(block["collection_prefix"]),
            embeddings=EmbeddingsSettings(
                model_name=str(embeddings_block["model_name"]),
                openrouter_api_key=str(embeddings_block["openrouter_api_key"]),
            ),
        )
