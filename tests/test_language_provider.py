import json
import logging
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ConfigDict

from yoda.mind.perception.language import LanguageProvider, StructuredOutputError


class _TinyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


@pytest.mark.asyncio
async def test_parse_structured_raises_StructuredOutputError_on_bad_json():
    llm = AsyncMock()
    llm.parse_chat_async.side_effect = json.JSONDecodeError("msg", "doc", 0)
    provider = LanguageProvider({"model_name": "m"}, llm)

    with pytest.raises(StructuredOutputError) as exc_info:
        await provider.parse_structured([{"role": "user", "content": "x"}], _TinyModel)

    assert "secret" not in str(exc_info.value)
    assert "msg" not in str(exc_info.value)
    assert str(exc_info.value) == "StructuredOutputError"


@pytest.mark.asyncio
async def test_parse_structured_raises_StructuredOutputError_on_validation(caplog):
    from pydantic import ValidationError

    llm = AsyncMock()
    try:
        _TinyModel(value=1)  # type: ignore[arg-type]
    except ValidationError as exc:
        llm.parse_chat_async.side_effect = exc

    provider = LanguageProvider({"model_name": "m"}, llm)

    with caplog.at_level(logging.DEBUG, logger="yoda.mind.perception.language"):
        with pytest.raises(StructuredOutputError) as exc_info:
            await provider.parse_structured([], _TinyModel)

    assert "validation" not in str(exc_info.value).lower()
    assert "1" not in str(exc_info.value)
    provider_records = [
        record for record in caplog.records
        if record.name == "yoda.mind.perception.language"
    ]
    assert any(record.levelno == logging.DEBUG for record in provider_records)
    assert all(record.levelno < logging.WARNING for record in provider_records)


@pytest.mark.asyncio
async def test_parse_structured_reraises_other_errors():
    llm = AsyncMock()
    llm.parse_chat_async.side_effect = RuntimeError("provider down")
    provider = LanguageProvider({"model_name": "m"}, llm)

    with pytest.raises(RuntimeError, match="provider down"):
        await provider.parse_structured([], _TinyModel)


def test_model_name_exposes_configured_model_id() -> None:
    provider = LanguageProvider({"model_name": "gpt-test-model"}, AsyncMock())
    assert provider.model_name == "gpt-test-model"
