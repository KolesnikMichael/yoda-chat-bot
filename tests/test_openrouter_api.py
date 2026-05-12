import pytest

from yoda.api.openrouter_api import OpenRouterApi


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
