from dataclasses import dataclass

from yoda.api.inference.data import BackendName, ConfiguredInference, ResolvedInference

_OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class _ProviderRecord:
    backend: BackendName
    api_key: str
    base_url: str | None


@dataclass(frozen=True)
class _ProfileRecord:
    provider_id: str
    model_name: str


class InferenceCatalogCore:
    def __init__(
        self,
        providers: dict[str, _ProviderRecord],
        profiles: dict[str, _ProfileRecord],
    ) -> None:
        self._providers = providers
        self._profiles = profiles

    @staticmethod
    def from_settings(settings: dict) -> "InferenceCatalogCore":
        inference = settings.get("inference")
        if not isinstance(inference, dict):
            raise ValueError("Settings missing required key: inference")
        providers = _non_empty_object(inference, "providers")
        profiles = _non_empty_object(inference, "profiles")
        return InferenceCatalogCore(
            providers={
                provider_id: _provider_record(provider_id, entry)
                for provider_id, entry in providers.items()
            },
            profiles={
                profile_id: _profile_record(profile_id, entry, providers)
                for profile_id, entry in profiles.items()
            },
        )

    def resolve(self, profile_id: str) -> ResolvedInference:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise ValueError(f"Unknown inference profile: '{profile_id}'")
        provider = self._providers[profile.provider_id]
        return ResolvedInference(
            profile_id=profile_id,
            provider_id=profile.provider_id,
            backend=provider.backend,
            api_key=provider.api_key,
            base_url=provider.base_url,
            model_name=profile.model_name,
        )

    @staticmethod
    def resolve_configured(settings: dict) -> ConfiguredInference:
        catalog = InferenceCatalogCore.from_settings(settings)
        language = catalog.resolve(_model_id(settings, "mind.perception.language.model"))
        agent = catalog.resolve(_model_id(settings, "agent.model"))
        summarizer = catalog.resolve(_model_id(settings, "mind.memory.summarizer.model"))
        vision = catalog.resolve(_model_id(settings, "mind.perception.vision.model"))
        embeddings = catalog.resolve(_model_id(settings, "mind.memory.summary_store.embeddings.model"))
        if embeddings.backend != "openrouter":
            raise ValueError(
                f"Embeddings profile '{embeddings.profile_id}' requires backend 'openrouter', "
                f"got '{embeddings.backend}'"
            )
        return ConfiguredInference(
            language=language,
            agent=agent,
            summarizer=summarizer,
            vision=vision,
            embeddings=embeddings,
        )


def _model_id(settings: dict, dotted: str) -> str:
    current: object = settings
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"Settings missing required inference model: {dotted}")
        current = current[part]
    if not isinstance(current, str) or not current:
        raise ValueError(f"Settings missing required inference model: {dotted}")
    return current


def _non_empty_object(parent: dict, key: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict) or len(value) == 0:
        raise ValueError(f"inference.{key} must be a non-empty object")
    return value


def _missing(kind: str, owner_id: str, field: str) -> ValueError:
    return ValueError(f"Inference {kind} '{owner_id}' missing required field '{field}'")


def _mapping(entry: object, kind: str, owner_id: str) -> dict:
    if not isinstance(entry, dict):
        raise _missing(kind, owner_id, "backend" if kind == "provider" else "provider")
    return entry


def _provider_record(provider_id: str, entry: object) -> _ProviderRecord:
    block = _mapping(entry, "provider", provider_id)
    if "backend" not in block:
        raise _missing("provider", provider_id, "backend")
    backend = block["backend"]
    if backend == "mistral":
        if "base_url" in block:
            raise ValueError(f"Inference provider '{provider_id}' does not support base_url")
        base_url = None
    elif backend == "openrouter":
        base_url = _openrouter_base_url(provider_id, block)
    else:
        raise ValueError(f"Inference provider '{provider_id}' has unknown backend '{backend}'")
    if "api_key" not in block or not isinstance(block["api_key"], str) or not block["api_key"].strip():
        raise _missing("provider", provider_id, "api_key")
    return _ProviderRecord(backend=backend, api_key=block["api_key"].strip(), base_url=base_url)


def _openrouter_base_url(provider_id: str, block: dict) -> str:
    if "base_url" not in block:
        return _OPENROUTER_DEFAULT_BASE_URL
    raw = block["base_url"]
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Inference provider '{provider_id}' has invalid base_url")
    base_url = raw.strip().rstrip("/")
    if not base_url:
        raise ValueError(f"Inference provider '{provider_id}' has invalid base_url")
    return base_url


def _profile_record(profile_id: str, entry: object, providers: dict) -> _ProfileRecord:
    block = _mapping(entry, "profile", profile_id)
    if "provider" not in block or not isinstance(block["provider"], str) or not block["provider"]:
        raise _missing("profile", profile_id, "provider")
    provider_id = block["provider"]
    if "model_name" not in block or not isinstance(block["model_name"], str) or not block["model_name"].strip():
        raise _missing("profile", profile_id, "model_name")
    if provider_id not in providers:
        raise ValueError(
            f"Inference profile '{profile_id}' references unknown provider '{provider_id}'"
        )
    return _ProfileRecord(provider_id=provider_id, model_name=block["model_name"].strip())
