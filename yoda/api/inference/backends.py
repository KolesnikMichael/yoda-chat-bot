from pathlib import Path

from yoda.api.chat_backend import ChatBackend
from yoda.api.embeddings_api import EmbeddingsApi
from yoda.api.inference.data import ResolvedInference
from yoda.api.mistral_api import MistralApi
from yoda.api.openrouter_api import OpenRouterApi


def build_chat_backend(
    resolved: ResolvedInference,
    debug_log_dir: Path | None = None,
) -> ChatBackend:
    if resolved.backend == "mistral":
        return MistralApi(resolved.api_key, debug_log_dir=debug_log_dir)
    if resolved.backend == "openrouter":
        return OpenRouterApi(resolved.api_key, base_url=_openrouter_base_url(resolved))
    raise ValueError(
        f"Inference provider '{resolved.provider_id}' has unknown backend '{resolved.backend}'"
    )


def build_embeddings_api(resolved: ResolvedInference) -> EmbeddingsApi:
    if resolved.backend != "openrouter":
        raise ValueError(
            f"Embeddings profile '{resolved.profile_id}' requires backend 'openrouter', "
            f"got '{resolved.backend}'"
        )
    return EmbeddingsApi(resolved.api_key, base_url=_openrouter_base_url(resolved))


def _openrouter_base_url(resolved: ResolvedInference) -> str:
    if not resolved.base_url:
        raise ValueError(f"Inference provider '{resolved.provider_id}' has invalid base_url")
    return resolved.base_url
