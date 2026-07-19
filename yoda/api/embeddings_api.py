"""Async façade for OpenRouter embeddings (OpenAI-compatible API)."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class EmbeddingsApi:
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def embed(self, model_name: str, texts: list[str]) -> list[list[float]]:
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model_name,
            "input": texts,
        }
        timeout = httpx.Timeout(120.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = response.text[:2000]
            logger.error("Embeddings HTTP %s: %s", response.status_code, body)
            raise ValueError(
                f"Embeddings request failed: {response.status_code}"
            ) from e

        try:
            data = response.json()
        except ValueError as err:
            body = response.text[:2000]
            logger.error("Embeddings parse failure: %s", body)
            raise ValueError("Embeddings response is not valid JSON") from err

        try:
            items = data["data"]
            sorted_items = sorted(items, key=lambda item: item["index"])
            return [item["embedding"] for item in sorted_items]
        except (KeyError, TypeError, IndexError) as err:
            raise ValueError(
                f"Unexpected embeddings response shape: {data!r}"
            ) from err
