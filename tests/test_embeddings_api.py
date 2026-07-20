import pytest

from yoda.api.embeddings_api import EmbeddingsApi


@pytest.mark.asyncio
async def test_embeddings_api_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "data": [
                    {"index": 1, "embedding": [0.2, 0.3]},
                    {"index": 0, "embedding": [0.0, 0.1]},
                ]
            }

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

    monkeypatch.setattr("yoda.api.embeddings_api.httpx.AsyncClient", FakeClient)

    api = EmbeddingsApi(api_key="sk-test")
    vectors = await api.embed("openai/text-embedding-3-small", ["a", "b"])

    assert vectors == [[0.0, 0.1], [0.2, 0.3]]
    assert captured["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert captured["body"] == {
        "model": "openai/text-embedding-3-small",
        "input": ["a", "b"],
    }
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_embeddings_api_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    class FakeResponse:
        status_code = 500
        text = "server error"

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "https://example.com"),
                response=self,
            )

        def json(self) -> dict:
            return {}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("yoda.api.embeddings_api.httpx.AsyncClient", FakeClient)

    api = EmbeddingsApi(api_key="sk-test")
    with pytest.raises(ValueError, match="Embeddings request failed: 500"):
        await api.embed("openai/text-embedding-3-small", ["x"])


@pytest.mark.asyncio
async def test_embeddings_api_malformed_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200
        text = "not-json"

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            raise ValueError("bad json")

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("yoda.api.embeddings_api.httpx.AsyncClient", FakeClient)

    api = EmbeddingsApi(api_key="sk-test")
    with pytest.raises(ValueError, match="not valid JSON"):
        await api.embed("openai/text-embedding-3-small", ["x"])


@pytest.mark.asyncio
async def test_embeddings_api_unexpected_shape_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"unexpected": True}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("yoda.api.embeddings_api.httpx.AsyncClient", FakeClient)

    api = EmbeddingsApi(api_key="sk-test")
    with pytest.raises(ValueError, match="Unexpected embeddings response shape"):
        await api.embed("openai/text-embedding-3-small", ["x"])
