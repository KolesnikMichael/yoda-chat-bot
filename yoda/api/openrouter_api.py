"""Async façade for OpenRouter chat completions (OpenAI-compatible API)."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterApi:
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        timeout = httpx.Timeout(120.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = response.text[:2000]
            logger.error("OpenRouter HTTP %s: %s", response.status_code, body)
            raise ValueError(
                f"OpenRouter request failed: {response.status_code}"
            ) from e

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as err:
            raise ValueError(
                f"Unexpected OpenRouter response shape: {data!r}"
            ) from err
        if content is None:
            raise ValueError(f"OpenRouter returned empty message content: {data!r}")
        return content
