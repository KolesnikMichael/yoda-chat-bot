import asyncio
from mistralai.client import Mistral


class LLMApi:
    def __init__(self, api_key: str):
        self._client = Mistral(api_key=api_key)

    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
        response = await self._client.chat.complete_async(model=model_name, messages=messages)
        return response.choices[0].message.content

    async def complete_chat_via_thread(self, model_name: str, messages: list[dict]) -> str:
        response = await asyncio.to_thread(self._client.chat.complete, model=model_name, messages=messages)
        return response.choices[0].message.content
