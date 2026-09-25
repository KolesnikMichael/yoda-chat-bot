"""Async façade for OpenRouter chat completions (OpenAI-compatible API)."""

import json
import logging
from typing import Any, cast

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterApi:
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
        return cast(str, await self._message_content(model_name, messages))

    async def parse_chat_async(
        self,
        model_name: str,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        content = await self._message_content(
            model_name,
            messages,
            response_format={"type": "json_object"},
        )
        if not isinstance(content, str):
            raise ValueError("OpenRouter structured content is not a string")
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.debug(f"OpenRouter returned invalid JSON: {content[:500]}")
            raise
        return response_format.model_validate(data)

    async def _message_content(
        self,
        model_name: str,
        messages: list[dict],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> object:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
        }
        if response_format is not None:
            payload["response_format"] = response_format
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
        if content is None and response_format is None:
            raise ValueError(f"OpenRouter returned empty message content: {data!r}")
        return content
