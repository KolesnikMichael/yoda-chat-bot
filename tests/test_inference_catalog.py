import json
import re
from pathlib import Path

import pytest

from yoda.api.embeddings_api import EmbeddingsApi
from yoda.api.inference.backends import build_chat_backend, build_embeddings_api
from yoda.api.inference.catalog import InferenceCatalogCore
from yoda.api.inference.data import ResolvedInference
from yoda.api.mistral_api import MistralApi
from yoda.api.openrouter_api import OpenRouterApi


def _settings(
    *,
    providers: dict | None = None,
    profiles: dict | None = None,
    include_providers: bool = True,
    include_profiles: bool = True,
) -> dict:
    inference: dict = {}
    if include_providers:
        inference["providers"] = (
            {
                "mistral": {"backend": "mistral", "api_key": "mistral-key"},
                "openrouter": {"backend": "openrouter", "api_key": "openrouter-key"},
            }
            if providers is None
            else providers
        )
    if include_profiles:
        inference["profiles"] = (
            {
                "text": {"provider": "openrouter", "model_name": "qwen/qwen3.8-27b:free"},
            }
            if profiles is None
            else profiles
        )
    return {"inference": inference}


def test_from_settings_accepts_a_valid_catalog() -> None:
    catalog = InferenceCatalogCore.from_settings(_settings())
    assert isinstance(catalog, InferenceCatalogCore)


def test_from_settings_rejects_missing_or_non_object_inference() -> None:
    with pytest.raises(ValueError, match=r"^Settings missing required key: inference$"):
        InferenceCatalogCore.from_settings({})
    with pytest.raises(ValueError, match=r"^Settings missing required key: inference$"):
        InferenceCatalogCore.from_settings({"inference": ["not", "an", "object"]})


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (
            {"inference": {"profiles": {"text": {"provider": "openrouter", "model_name": "m"}}}},
            "inference.providers must be a non-empty object",
        ),
        (
            _settings(providers={}),
            "inference.providers must be a non-empty object",
        ),
        (
            _settings(providers=[]),  # type: ignore[arg-type]
            "inference.providers must be a non-empty object",
        ),
        (
            {"inference": {"providers": {"openrouter": {"backend": "openrouter", "api_key": "k"}}}},
            "inference.profiles must be a non-empty object",
        ),
        (
            _settings(profiles={}),
            "inference.profiles must be a non-empty object",
        ),
        (
            _settings(profiles=[]),  # type: ignore[arg-type]
            "inference.profiles must be a non-empty object",
        ),
    ],
)
def test_from_settings_rejects_empty_or_non_object_maps(settings: dict, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        InferenceCatalogCore.from_settings(settings)


@pytest.mark.parametrize(
    ("providers", "profiles", "message"),
    [
        (
            {"mistral": {"api_key": "k"}},
            {"text": {"provider": "mistral", "model_name": "ministral-14b-latest"}},
            "Inference provider 'mistral' missing required field 'backend'",
        ),
        (
            {"mistral": {"backend": "mistral"}},
            {"text": {"provider": "mistral", "model_name": "ministral-14b-latest"}},
            "Inference provider 'mistral' missing required field 'api_key'",
        ),
        (
            {"mistral": {"backend": "mistral", "api_key": "   "}},
            {"text": {"provider": "mistral", "model_name": "ministral-14b-latest"}},
            "Inference provider 'mistral' missing required field 'api_key'",
        ),
        (
            {"mistral": {"backend": "mistral", "api_key": 12}},
            {"text": {"provider": "mistral", "model_name": "ministral-14b-latest"}},
            "Inference provider 'mistral' missing required field 'api_key'",
        ),
        (
            {"openrouter": {"backend": "openrouter", "api_key": "k"}},
            {"text": {"model_name": "qwen/qwen3.8-27b:free"}},
            "Inference profile 'text' missing required field 'provider'",
        ),
        (
            {"openrouter": {"backend": "openrouter", "api_key": "k"}},
            {"text": {"provider": "openrouter"}},
            "Inference profile 'text' missing required field 'model_name'",
        ),
        (
            {"openrouter": {"backend": "openrouter", "api_key": "k"}},
            {"text": {"provider": "openrouter", "model_name": "  "}},
            "Inference profile 'text' missing required field 'model_name'",
        ),
    ],
)
def test_from_settings_rejects_missing_fields(
    providers: dict,
    profiles: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        InferenceCatalogCore.from_settings(_settings(providers=providers, profiles=profiles))


def test_from_settings_rejects_unknown_backend_without_leaking_the_key() -> None:
    secret = "super-secret-key"
    settings = _settings(
        providers={"custom": {"backend": "jev", "api_key": secret}},
        profiles={"text": {"provider": "custom", "model_name": "some-model"}},
    )
    with pytest.raises(
        ValueError,
        match=r"^Inference provider 'custom' has unknown backend 'jev'$",
    ) as caught:
        InferenceCatalogCore.from_settings(settings)
    assert secret not in str(caught.value)


def test_from_settings_rejects_mistral_base_url() -> None:
    settings = _settings(
        providers={"mistral": {"backend": "mistral", "api_key": "k", "base_url": "https://api.mistral.ai"}},
        profiles={"text": {"provider": "mistral", "model_name": "ministral-14b-latest"}},
    )
    with pytest.raises(
        ValueError,
        match=r"^Inference provider 'mistral' does not support base_url$",
    ):
        InferenceCatalogCore.from_settings(settings)


@pytest.mark.parametrize("base_url", ["", "   ", 15, None])
def test_from_settings_rejects_invalid_openrouter_base_url(base_url: object) -> None:
    settings = _settings(
        providers={
            "openrouter": {
                "backend": "openrouter",
                "api_key": "k",
                "base_url": base_url,
            }
        },
        profiles={"text": {"provider": "openrouter", "model_name": "qwen/qwen3.8-27b:free"}},
    )
    with pytest.raises(
        ValueError,
        match=r"^Inference provider 'openrouter' has invalid base_url$",
    ):
        InferenceCatalogCore.from_settings(settings)


def test_from_settings_rejects_unknown_provider_on_an_unused_profile() -> None:
    settings = _settings(
        profiles={
            "text": {"provider": "openrouter", "model_name": "qwen/qwen3.8-27b:free"},
            "orphan": {"provider": "missing", "model_name": "other"},
        }
    )
    with pytest.raises(
        ValueError,
        match=r"^Inference profile 'orphan' references unknown provider 'missing'$",
    ):
        InferenceCatalogCore.from_settings(settings)


def _example_settings() -> dict:
    return {
        "inference": {
            "providers": {
                "mistral": {"backend": "mistral", "api_key": "mistral-key"},
                "openrouter": {
                    "backend": "openrouter",
                    "api_key": "openrouter-key",
                    "base_url": "https://openrouter.ai/api/v1/",
                },
            },
            "profiles": {
                "text_qwen27_free": {
                    "provider": "openrouter",
                    "model_name": "qwen/qwen3.8-27b:free",
                },
                "text_ministral14": {
                    "provider": "mistral",
                    "model_name": "ministral-14b-latest",
                },
                "vision_qwen_vl": {
                    "provider": "openrouter",
                    "model_name": "qwen/qwen3-vl-235b-a22b-thinking",
                },
                "embed_openai_small": {
                    "provider": "openrouter",
                    "model_name": "openai/text-embedding-3-small",
                },
            },
        },
        "mind": {
            "perception": {
                "language": {"model": "text_qwen27_free"},
                "vision": {"model": "vision_qwen_vl"},
            },
            "memory": {
                "summarizer": {"model": "text_qwen27_free"},
                "summary_store": {"embeddings": {"model": "embed_openai_small"}},
            },
        },
        "agent": {"model": "text_qwen27_free"},
    }


def _drop_selector(settings: dict, dotted: str) -> dict:
    current = settings
    parts = dotted.split(".")
    for part in parts[:-1]:
        current = current[part]
    del current[parts[-1]]
    return settings


def test_resolve_unknown_profile_names_the_id() -> None:
    catalog = InferenceCatalogCore.from_settings(_settings())
    with pytest.raises(ValueError, match=r"^Unknown inference profile: 'no-such-profile'$"):
        catalog.resolve("no-such-profile")


def test_resolve_strips_credentials_and_normalizes_base_url() -> None:
    catalog = InferenceCatalogCore.from_settings(
        _settings(
            providers={
                "openrouter": {
                    "backend": "openrouter",
                    "api_key": "  router-key  ",
                    "base_url": "https://example.com/v1/",
                }
            },
            profiles={"text": {"provider": "openrouter", "model_name": "  qwen/model  "}},
        )
    )
    resolved = catalog.resolve("text")
    assert resolved == ResolvedInference(
        profile_id="text",
        provider_id="openrouter",
        backend="openrouter",
        api_key="router-key",
        base_url="https://example.com/v1",
        model_name="qwen/model",
    )


def test_resolve_omitted_openrouter_base_url_uses_the_default() -> None:
    catalog = InferenceCatalogCore.from_settings(_settings())
    resolved = catalog.resolve("text")
    assert resolved.base_url == "https://openrouter.ai/api/v1"
    assert resolved.backend == "openrouter"


def test_example_profiles_resolve_to_qwen_and_ministral() -> None:
    catalog = InferenceCatalogCore.from_settings(_example_settings())
    qwen = catalog.resolve("text_qwen27_free")
    ministral = catalog.resolve("text_ministral14")
    assert qwen.backend == "openrouter"
    assert qwen.model_name == "qwen/qwen3.8-27b:free"
    assert qwen.base_url == "https://openrouter.ai/api/v1"
    assert ministral.backend == "mistral"
    assert ministral.model_name == "ministral-14b-latest"
    assert ministral.base_url is None


def test_language_and_agent_resolve_independently() -> None:
    settings = _example_settings()
    settings["agent"]["model"] = "text_ministral14"
    configured = InferenceCatalogCore.resolve_configured(settings)
    assert configured.language.backend == "openrouter"
    assert configured.language.model_name == "qwen/qwen3.8-27b:free"
    assert configured.agent.backend == "mistral"
    assert configured.agent.model_name == "ministral-14b-latest"
    assert configured.summarizer.profile_id == "text_qwen27_free"
    assert configured.vision.model_name == "qwen/qwen3-vl-235b-a22b-thinking"
    assert configured.embeddings.model_name == "openai/text-embedding-3-small"
    assert configured.embeddings.backend == "openrouter"


def test_resolve_configured_rejects_non_openrouter_embeddings() -> None:
    settings = _example_settings()
    settings["mind"]["memory"]["summary_store"]["embeddings"]["model"] = "text_ministral14"
    with pytest.raises(
        ValueError,
        match=r"^Embeddings profile 'text_ministral14' requires backend 'openrouter', got 'mistral'$",
    ):
        InferenceCatalogCore.resolve_configured(settings)


@pytest.mark.parametrize(
    "dotted",
    [
        "mind.perception.language.model",
        "agent.model",
        "mind.memory.summarizer.model",
        "mind.perception.vision.model",
        "mind.memory.summary_store.embeddings.model",
    ],
)
def test_resolve_configured_requires_each_consumer_model(dotted: str) -> None:
    settings = _drop_selector(_example_settings(), dotted)
    with pytest.raises(ValueError, match=f"^{re.escape(f'Settings missing required inference model: {dotted}')}$"):
        InferenceCatalogCore.resolve_configured(settings)


def test_build_chat_backend_returns_the_matching_facade() -> None:
    mistral = build_chat_backend(
        ResolvedInference(
            profile_id="text_ministral14",
            provider_id="mistral",
            backend="mistral",
            api_key="mistral-key",
            base_url=None,
            model_name="ministral-14b-latest",
        )
    )
    openrouter = build_chat_backend(
        ResolvedInference(
            profile_id="text_qwen27_free",
            provider_id="openrouter",
            backend="openrouter",
            api_key="router-key",
            base_url="https://example.com/v1",
            model_name="qwen/qwen3.8-27b:free",
        )
    )
    assert isinstance(mistral, MistralApi)
    assert isinstance(openrouter, OpenRouterApi)
    assert openrouter._base_url == "https://example.com/v1"


def test_build_embeddings_api_requires_openrouter() -> None:
    mistral = ResolvedInference(
        profile_id="text_ministral14",
        provider_id="mistral",
        backend="mistral",
        api_key="mistral-key",
        base_url=None,
        model_name="ministral-14b-latest",
    )
    with pytest.raises(
        ValueError,
        match=r"^Embeddings profile 'text_ministral14' requires backend 'openrouter', got 'mistral'$",
    ):
        build_embeddings_api(mistral)

    embeddings = build_embeddings_api(
        ResolvedInference(
            profile_id="embed_openai_small",
            provider_id="openrouter",
            backend="openrouter",
            api_key="router-key",
            base_url="https://example.com/v1/",
            model_name="openai/text-embedding-3-small",
        )
    )
    assert isinstance(embeddings, EmbeddingsApi)
    assert embeddings._base_url == "https://example.com/v1"


def test_repo_settings_resolve_the_committed_profiles() -> None:
    settings_path = Path(__file__).resolve().parents[1] / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    configured = InferenceCatalogCore.resolve_configured(settings)
    for consumer in (configured.language, configured.agent, configured.summarizer):
        assert consumer.profile_id == "text_qwen27_free"
        assert consumer.backend == "openrouter"
        assert consumer.model_name == "qwen/qwen3.8-27b:free"
    assert configured.vision.profile_id == "vision_qwen_vl"
    assert configured.vision.backend == "openrouter"
    assert configured.vision.model_name == "qwen/qwen3-vl-235b-a22b-thinking"
    assert configured.embeddings.profile_id == "embed_openai_small"
    assert configured.embeddings.backend == "openrouter"
    assert configured.embeddings.model_name == "openai/text-embedding-3-small"
    ministral = InferenceCatalogCore.from_settings(settings).resolve("text_ministral14")
    assert ministral.backend == "mistral"
    assert ministral.model_name == "ministral-14b-latest"

    assert "llm" not in settings
    perception = settings["mind"]["perception"]
    assert "openrouter" not in perception
    assert "api_key" not in perception["language"]
    assert "model_name" not in perception["language"]
    assert "provider" not in perception["vision"]
    assert "api_key" not in perception["vision"]
    assert "model_name" not in perception["vision"]
    embeddings = settings["mind"]["memory"]["summary_store"]["embeddings"]
    assert set(embeddings) == {"model"}
    assert "model_name" not in settings["agent"]
