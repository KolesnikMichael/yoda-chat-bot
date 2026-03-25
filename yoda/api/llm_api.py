import asyncio
import json
import logging

from mistralai.client import Mistral
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMApi:
    def __init__(self, api_key: str):
        self._client = Mistral(api_key=api_key)

    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
        response = await self._client.chat.complete_async(model=model_name, messages=messages)
        return response.choices[0].message.content

    async def complete_chat_via_thread(self, model_name: str, messages: list[dict]) -> str:
        response = await asyncio.to_thread(self._client.chat.complete, model=model_name, messages=messages)
        return response.choices[0].message.content

    async def parse_chat_async(
        self,
        model_name: str,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        response = await self._client.chat.complete_async(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        logger.debug(f"LLM raw JSON response: {content[:1000]}")
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"LLM returned invalid JSON: {content[:500]}")
            raise
        return response_format(**data)
