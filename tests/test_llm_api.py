import json
import re
from pathlib import Path

from yoda.api.llm_api import (
    LLMApi,
    _format_debug_exchange_md,
    _write_debug_exchange,
)


def test_format_debug_exchange_md_multiline_messages_and_pretty_json_response() -> None:
    md = _format_debug_exchange_md(
        timestamp="2026-07-20T10:00:00.123Z",
        method="parse_chat_async",
        model="mistral-small",
        messages=[
            {"role": "system", "content": "line one\nline two"},
            {"role": "user", "content": "Привет"},
        ],
        response='{"answer": "да"}',
    )

    assert md.startswith("# 2026-07-20T10:00:00.123Z | parse_chat_async | mistral-small")
    assert "## [system]" in md
    assert "line one\nline two" in md
    assert "## [user]" in md
    assert "Привет" in md
    assert "## Response" in md
    assert '{\n  "answer": "да"\n}' in md


def test_write_debug_exchange_creates_md_file(tmp_path: Path) -> None:
    path = _write_debug_exchange(
        tmp_path,
        method="parse_chat_async",
        model="mistral-small",
        messages=[{"role": "user", "content": "Hello"}],
        response='{"answer": "yes"}',
    )

    assert path.parent == tmp_path
    assert re.fullmatch(r"\d{4}_\d{2}_\d{2}-\d{2}_\d{2}_\d{2}-\d{3}\.md", path.name)
    text = path.read_text(encoding="utf-8")
    assert "| parse_chat_async | mistral-small" in text
    assert "## [user]" in text
    assert "Hello" in text
    assert '"answer": "yes"' in text


def test_format_debug_exchange_md_non_json_response() -> None:
    md = _format_debug_exchange_md(
        timestamp="2026-07-20T10:00:00Z",
        method="complete_chat_async",
        model="m",
        messages=[],
        response="plain text\nsecond line",
    )

    assert "## Response" in md
    assert "plain text\nsecond line" in md


def test_llm_api_skips_logging_when_debug_dir_is_none() -> None:
    api = LLMApi(api_key="test-key", debug_log_dir=None)
    api._log_exchange("complete_chat_async", "m", [], "ok")
