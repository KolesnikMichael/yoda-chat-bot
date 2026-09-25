import json

import pytest
from pydantic import BaseModel

from yoda.api.openrouter_api import OpenRouterApi


class _TinyModel(BaseModel):
    answer: str


def _patch_client(monkeypatch: pytest.MonkeyPatch, content: object, captured: dict) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": content}}]}

        text = ""

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self, url: str, json: dict | None = None, headers: dict | None = None
        ) -> FakeResponse:
            captured["url"] = url
            captured["body"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("yoda.api.openrouter_api.httpx.AsyncClient", FakeClient)


@pytest.mark.asyncio
async def test_openrouter_api_complete_chat_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "A cat."}}]}

        text = ""

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self, url: str, json: dict | None = None, headers: dict | None = None
        ) -> FakeResponse:
            captured["url"] = url
            captured["body"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(
        "yoda.api.openrouter_api.httpx.AsyncClient",
        FakeClient,
    )

    api = OpenRouterApi(api_key="sk-test", base_url="https://openrouter.ai/api/v1")
    out = await api.complete_chat_async(
        "google/gemma-4-31b-it:free",
        [{"role": "user", "content": "hi"}],
    )

    assert out == "A cat."
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["body"]["model"] == "google/gemma-4-31b-it:free"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_openrouter_api_strips_base_url_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "x"}}]}

        text = ""

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self, url: str, json: dict | None = None, headers: dict | None = None
        ) -> FakeResponse:
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr(
        "yoda.api.openrouter_api.httpx.AsyncClient",
        FakeClient,
    )

    api = OpenRouterApi(api_key="k", base_url="https://example.com/api/v1/")
    await api.complete_chat_async("m", [])
    assert captured["url"] == "https://example.com/api/v1/chat/completions"


@pytest.mark.asyncio
async def test_openrouter_api_missing_content_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": None}}]}

        text = ""

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self, url: str, json: dict | None = None, headers: dict | None = None
        ) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(
        "yoda.api.openrouter_api.httpx.AsyncClient",
        FakeClient,
    )

    api = OpenRouterApi(api_key="k")
    with pytest.raises(ValueError, match="empty message content"):
        await api.complete_chat_async("m", [])


@pytest.mark.asyncio
async def test_openrouter_parse_chat_validates_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    _patch_client(monkeypatch, '{"answer": "yes"}', captured)
    api = OpenRouterApi(api_key="sk-test")
    parsed = await api.parse_chat_async(
        "qwen/qwen3.8-27b:free",
        [{"role": "user", "content": "hi"}],
        _TinyModel,
    )
    assert parsed == _TinyModel(answer="yes")
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["model"] == "qwen/qwen3.8-27b:free"


@pytest.mark.asyncio
async def test_openrouter_parse_chat_invalid_json_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, "not-json", {})
    api = OpenRouterApi(api_key="sk-test")
    with pytest.raises(json.JSONDecodeError):
        await api.parse_chat_async("m", [], _TinyModel)


@pytest.mark.asyncio
async def test_openrouter_parse_chat_non_string_content_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, ["not", "a", "string"], {})
    api = OpenRouterApi(api_key="sk-test")
    with pytest.raises(ValueError, match=r"^OpenRouter structured content is not a string$"):
        await api.parse_chat_async("m", [], _TinyModel)
