import json
import logging

from pydantic import BaseModel, ValidationError

from yoda.api.chat_backend import ChatBackend

logger = logging.getLogger(__name__)


class StructuredOutputError(Exception):
    """Structured LLM output failed shape/JSON validation (no raw content)."""

    def __str__(self) -> str:
        return self.__class__.__name__


class LanguageProvider:
    def __init__(self, settings: dict, chat_backend: ChatBackend):
        self._chat_backend = chat_backend
        try:
            self._model_name = settings["model_name"]
        except KeyError as e:
            raise ValueError(
                "Language settings missing required 'model_name'") from e

    @property
    def model_name(self) -> str:
        return self._model_name

    async def reply_in_conversation(self, conversation: list[dict]) -> str:
        return await self._chat_backend.complete_chat_async(
            model_name=self._model_name,
            messages=conversation,
        )

    async def parse_structured(
        self,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        try:
            return await self._chat_backend.parse_chat_async(
                model_name=self._model_name,
                messages=messages,
                response_format=response_format,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.debug("Structured output parse failed")
            raise StructuredOutputError() from exc
