import asyncio
import datetime as dtm
import json
import logging
from pathlib import Path

from mistralai.client import Mistral
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _format_response_block(response: str) -> str:
    try:
        parsed = json.loads(response)
        formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
        return f"```json\n{formatted}\n```"
    except json.JSONDecodeError:
        return f"```\n{response}\n```"


def _format_debug_exchange_md(
    *,
    timestamp: str,
    method: str,
    model: str,
    messages: list[dict],
    response: str,
) -> str:
    lines = [f"# {timestamp} | {method} | {model}", ""]
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        lines.extend([f"## [{role}]", "", content, ""])
    lines.extend(["## Response", "", _format_response_block(response)])
    return "\n".join(lines)


def _write_debug_exchange(
    log_dir: Path,
    *,
    method: str,
    model: str,
    messages: list[dict],
    response: str,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    now = dtm.datetime.now(dtm.UTC)
    filename = (
        f"{now.strftime('%Y_%m_%d-%H_%M_%S')}-{now.microsecond // 1000:03d}.md"
    )
    path = log_dir / filename
    timestamp = now.isoformat().replace("+00:00", "Z")
    path.write_text(
        _format_debug_exchange_md(
            timestamp=timestamp,
            method=method,
            model=model,
            messages=messages,
            response=response,
        ),
        encoding="utf-8",
    )
    logger.debug("LLM exchange logged to %s", path)
    return path


class MistralApi:
    def __init__(self, api_key: str, debug_log_dir: Path | None = None):
        self._client = Mistral(api_key=api_key)
        self._debug_log_dir = debug_log_dir

    def _log_exchange(
        self,
        method: str,
        model_name: str,
        messages: list[dict],
        response: str,
    ) -> None:
        if self._debug_log_dir is None:
            return
        _write_debug_exchange(
            self._debug_log_dir,
            method=method,
            model=model_name,
            messages=messages,
            response=response,
        )

    async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
        response = await self._client.chat.complete_async(model=model_name, messages=messages)
        content = response.choices[0].message.content or ""
        self._log_exchange("complete_chat_async", model_name, messages, content)
        return content

    async def complete_chat_via_thread(self, model_name: str, messages: list[dict]) -> str:
        response = await asyncio.to_thread(
            self._client.chat.complete, model=model_name, messages=messages,
        )
        content = response.choices[0].message.content or ""
        self._log_exchange("complete_chat_via_thread", model_name, messages, content)
        return content

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
        content = response.choices[0].message.content or ""
        self._log_exchange("parse_chat_async", model_name, messages, content)
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.debug(f"LLM returned invalid JSON: {content[:500]}")
            raise
        return response_format.model_validate(data)
