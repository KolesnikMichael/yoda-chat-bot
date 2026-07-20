import json
import logging

from pydantic import BaseModel, ValidationError

from yoda.api.llm_api import LLMApi

logger = logging.getLogger(__name__)


class StructuredOutputError(Exception):
    """Structured LLM output failed shape/JSON validation (no raw content)."""

    def __str__(self) -> str:
        return self.__class__.__name__


class LanguageProvider:
    def __init__(self, settings: dict, llm_api: LLMApi):
        self._llm_api = llm_api
        try:
            self._model_name = settings["model_name"]
        except KeyError as e:
            raise ValueError(
                "Language settings missing required 'model_name'") from e

    async def reply_in_conversation(self, conversation: list[dict]) -> str:
        return await self._llm_api.complete_chat_async(
            model_name=self._model_name,
            messages=conversation,
        )

    async def parse_structured(
        self,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        try:
            return await self._llm_api.parse_chat_async(
                model_name=self._model_name,
                messages=messages,
                response_format=response_format,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.debug("Structured output parse failed")
            raise StructuredOutputError() from exc
