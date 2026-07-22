"""Deterministic recorded adapters for routing evaluation (TASK-020)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from yoda.api.llm_api import LLMApi
from yoda.mind.agent.data.agent_data import (
    ExecutionDecision,
    SelectionDecision,
    ToolCall,
    ToolResult,
)
from yoda.mind.agent.data.outcome_data import TerminalResultFacts
from yoda.mind.cognition import IntentClassification
from yoda.mind.evaluation.data import RecordedModelResponse, RecordedToolResult


class RecordedLLMError(Exception):
    pass


_STAGE_BY_FORMAT: dict[type[BaseModel], str] = {
    IntentClassification: "intent",
    SelectionDecision: "selection",
    ExecutionDecision: "planning",
}


class RecordedLLMApi(LLMApi):
    def __init__(
        self,
        responses: list[RecordedModelResponse] | None = None,
        *,
        chat_reply: str = "Deterministic evaluation reply.",
    ) -> None:
        super().__init__(api_key="evaluation-test-key")
        self._queue = list(responses or [])
        self._chat_reply = chat_reply
        self.parse_calls: list[tuple[str, type[BaseModel]]] = []

    def set_queue(self, responses: list[RecordedModelResponse]) -> None:
        self._queue = list(responses)

    async def complete_chat_async(
        self,
        model_name: str,
        messages: list[dict],
    ) -> str:
        return self._chat_reply

    async def parse_chat_async(
        self,
        model_name: str,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        self.parse_calls.append((model_name, response_format))
        if not self._queue:
            raise RecordedLLMError(
                f"no recorded response for stage {_STAGE_BY_FORMAT.get(response_format, 'unknown')}",
            )
        expected_stage = _STAGE_BY_FORMAT.get(response_format)
        if expected_stage is None:
            raise RecordedLLMError(
                f"undeclared response format: {response_format.__name__}",
            )
        next_item = self._queue[0]
        if next_item.stage != expected_stage:
            raise RecordedLLMError(
                f"stage mismatch: expected {expected_stage}, next recorded is {next_item.stage}",
            )
        self._queue.pop(0)
        data = json.loads(next_item.raw)
        return response_format.model_validate(data)

    def assert_fully_consumed(self) -> None:
        if self._queue:
            remaining = ", ".join(item.stage for item in self._queue)
            raise RecordedLLMError(f"unused recorded model responses: {remaining}")


class InMemoryStorageApi:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, str]] = {}
        self.kv: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def set(self, key: str, value: str) -> None:
        self.kv[key] = value

    async def delete(self, key: str) -> None:
        self.kv.pop(key, None)

    async def hget(self, key: str, field: str) -> str | None:
        return self.data.get(key, {}).get(field)

    async def hset(self, key: str, field: str, value: str) -> int:
        bucket = self.data.setdefault(key, {})
        bucket[field] = value
        return 1

    async def hdel(self, key: str, field: str) -> int:
        bucket = self.data.get(key, {})
        if field in bucket:
            del bucket[field]
            return 1
        return 0

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.data.get(key, {}))

    async def keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [key for key in self.kv if key.startswith(prefix)]


@dataclass
class RecordedToolProvider:
    fixtures: list[RecordedToolResult] = field(default_factory=list)
    captured_calls: list[ToolCall] = field(default_factory=list)

    def set_fixtures(self, fixtures: list[RecordedToolResult]) -> None:
        self.fixtures = list(fixtures)
        self.captured_calls = []

    async def execute(self, call: ToolCall) -> ToolResult:
        self.captured_calls.append(call)
        if not self.fixtures:
            raise RecordedLLMError(
                f"no recorded tool result for {call.tool_name}",
            )
        next_fixture = self.fixtures[0]
        if next_fixture.tool_name != call.tool_name:
            raise RecordedLLMError(
                f"tool order mismatch: expected {next_fixture.tool_name}, got {call.tool_name}",
            )
        self.fixtures.pop(0)
        terminal_facts = next_fixture.terminal_facts
        if terminal_facts is not None and isinstance(terminal_facts, dict):
            terminal_facts = TerminalResultFacts(**terminal_facts)
        return ToolResult(
            tool_name=next_fixture.tool_name,
            output=next_fixture.output,
            success=next_fixture.success,
            suspend=next_fixture.suspend,
            terminal_facts=terminal_facts,
        )

    def assert_fully_consumed(self) -> None:
        if self.fixtures:
            remaining = ", ".join(item.tool_name for item in self.fixtures)
            raise RecordedLLMError(f"unused recorded tool fixtures: {remaining}")
