from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingsSettings:
    model_name: str


@dataclass(frozen=True)
class SummaryStoreSettings:
    persist_directory: str
    collection_prefix: str

    @classmethod
    def from_dict(cls, block: dict) -> "SummaryStoreSettings":
        required_keys = ("persist_directory", "collection_prefix")
        for key in required_keys:
            if key not in block:
                raise ValueError(f"Missing required key: {key}")

        return cls(
            persist_directory=str(block["persist_directory"]),
            collection_prefix=str(block["collection_prefix"]),
        )
