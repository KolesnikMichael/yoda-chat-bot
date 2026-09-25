from dataclasses import dataclass
from typing import Literal

BackendName = Literal["mistral", "openrouter"]


@dataclass(frozen=True)
class ResolvedInference:
    profile_id: str
    provider_id: str
    backend: BackendName
    api_key: str
    base_url: str | None
    model_name: str


@dataclass(frozen=True)
class ConfiguredInference:
    language: ResolvedInference
    agent: ResolvedInference
    summarizer: ResolvedInference
    vision: ResolvedInference
    embeddings: ResolvedInference
