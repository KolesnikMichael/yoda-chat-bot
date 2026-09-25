from typing import Protocol

from pydantic import BaseModel


class ChatBackend(Protocol):
    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str: ...

    async def parse_chat_async(
        self,
        model_name: str,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel: ...
