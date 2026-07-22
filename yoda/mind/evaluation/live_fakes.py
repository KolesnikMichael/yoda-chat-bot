"""Fail-on-call isolation stubs and live-eval local adapters (TASK-021)."""

from __future__ import annotations

from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.evaluation.data import RecordedToolResult


class ForbiddenSideEffectError(RuntimeError):
    """Raised when live eval touches a non-LLM external boundary."""


class FailOnCall:
    """Raises on any attribute access used as a call target."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, item: str) -> object:
        def _raise(*args: object, **kwargs: object) -> None:
            raise ForbiddenSideEffectError(
                f"live eval forbidden side effect: {self._name}.{item}",
            )

        return _raise

    async def __call__(self, *args: object, **kwargs: object) -> None:
        raise ForbiddenSideEffectError(
            f"live eval forbidden side effect: {self._name}()",
        )


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


class RecordedToolProvider:
    def __init__(self, results: list[RecordedToolResult] | None = None) -> None:
        self._queue = list(results or [])

    async def execute(self, call: ToolCall) -> ToolResult:
        if not self._queue:
            raise ForbiddenSideEffectError(
                f"no recorded tool result for {call.tool_name}",
            )
        next_item = self._queue.pop(0)
        if next_item.tool_name != call.tool_name:
            raise ForbiddenSideEffectError(
                f"tool mismatch: expected {next_item.tool_name}, got {call.tool_name}",
            )
        return ToolResult(
            tool_name=next_item.tool_name,
            output=next_item.output,
            success=next_item.success,
            suspend=next_item.suspend,
            terminal_facts=next_item.terminal_facts,
        )

    def assert_fully_consumed(self) -> None:
        if self._queue:
            remaining = ", ".join(item.tool_name for item in self._queue)
            raise ForbiddenSideEffectError(
                f"unused recorded tool results: {remaining}",
            )


def telegram_stub() -> FailOnCall:
    return FailOnCall("telegram")


def search_stub() -> FailOnCall:
    return FailOnCall("tavily")


def media_stub() -> FailOnCall:
    return FailOnCall("media")


def redis_stub() -> FailOnCall:
    return FailOnCall("redis")


def scheduler_stub() -> FailOnCall:
    return FailOnCall("scheduler")


def chroma_stub() -> FailOnCall:
    return FailOnCall("chroma")
