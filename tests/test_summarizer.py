import json
import logging

import pytest
from pydantic import ValidationError

from tests.fakes import FakeLLMApi
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.summarizer_envelope import (
    LlmSummarizerEnvelope,
    SummarizerValidationError,
)
from yoda.mind.memory.data.summarizer_prompt import SUMMARIZER_SYSTEM_PROMPT
from yoda.mind.memory.data.summarizer_result import SummarizerResult
from yoda.mind.memory.data.summarizer_settings import SummarizerSettings
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.summarizer import SummarizerCore, SummarizerProvider


def _msg(
    kind: str,
    *,
    text: str = "",
    timestamp: str = "2026-05-22T08:14:03Z",
    user_id: int | None = None,
    role: str = "system",
) -> Message:
    return Message(
        role=role,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        timestamp=timestamp,
        user_id=user_id,
    )


def _profile(**kwargs: object) -> UserProfile:
    return UserProfile(**kwargs)  # type: ignore[arg-type]


# --- Stage 1: Data DTOs ---


def test_summarizer_result_fields():
    result = SummarizerResult(
        summary="A summary",
        topics=["weather"],
        participants=[42],
        skills=["web_search"],
        profile_updates={42: {"location": "Berlin"}},
    )
    assert isinstance(result.summary, str)
    assert isinstance(result.topics, list)
    assert isinstance(result.participants, list)
    assert isinstance(result.skills, list)
    assert isinstance(result.profile_updates, dict)


def test_summarizer_settings_nested_block_wins():
    settings = {
        "mind": {
            "memory": {
                "chat_compression": {
                    "summarizer": {"model_name": "mistral-small"},
                },
            },
            "perception": {"language": {"model_name": "mistral-large"}},
        },
    }
    assert SummarizerSettings.from_settings(settings).model_name == "mistral-small"


def test_summarizer_settings_fallback_to_language_model():
    settings = {
        "mind": {
            "memory": {"chat_compression": {}},
            "perception": {"language": {"model_name": "mistral-large"}},
        },
    }
    assert SummarizerSettings.from_settings(settings).model_name == "mistral-large"


def test_summarizer_settings_missing_both_raises():
    with pytest.raises(ValueError, match="model name"):
        SummarizerSettings.from_settings({"mind": {}})


def test_summarizer_envelope_valid_wire():
    envelope = LlmSummarizerEnvelope(
        summary="text",
        topics=["topic"],
        profile_updates={"42": {"location": "Berlin"}},
    )
    assert envelope.summary == "text"


def test_summarizer_envelope_missing_key_raises():
    with pytest.raises(ValidationError):
        LlmSummarizerEnvelope(summary="text", topics=[])


def test_summarizer_prompt_non_empty_and_anchors():
    assert SUMMARIZER_SYSTEM_PROMPT
    assert "ROLE" in SUMMARIZER_SYSTEM_PROMPT
    assert "OUTPUT FORMAT" in SUMMARIZER_SYSTEM_PROMPT
    assert "profile_updates" in SUMMARIZER_SYSTEM_PROMPT


# --- Stage 2: Mechanical extraction ---


def test_extract_participants_mixed_kinds_deduped_sorted():
    chunk = [
        _msg("user", user_id=77),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=42),
        _msg("user", user_id=42),
        _msg("user", user_id=None),
        _msg("task_result", text="Tools used: web_search. Result: ok"),
    ]
    assert SummarizerCore.extract_participants(chunk) == [42, 77]


def test_extract_skills_tools_used_clause():
    chunk = [
        _msg(
            "task_result",
            text="[web_search] (OK) Tools used: web_search, create_picture. Result: done",
        ),
    ]
    assert SummarizerCore.extract_skills(chunk) == ["create_picture", "web_search"]


def test_extract_skills_none_skipped():
    chunk = [_msg("task_result", text="Reminder. Tools used: none. Done.")]
    assert SummarizerCore.extract_skills(chunk) == []


def test_extract_skills_absent_clause_on_reminder():
    chunk = [_msg("task_result", text="Scheduled reminder fired.")]
    assert SummarizerCore.extract_skills(chunk) == []


def test_extract_skills_union_sorted():
    chunk = [
        _msg("task_result", text="Tools used: beta, alpha. ok"),
        _msg("task_result", text="Tools used: gamma. ok"),
    ]
    assert SummarizerCore.extract_skills(chunk) == ["alpha", "beta", "gamma"]


# --- Stage 3: Context assembly ---


def test_build_context_message_profiles_and_chunk():
    chunk = [
        _msg("user", user_id=42, text="hello", timestamp="2026-05-22T08:14:03Z"),
        _msg("assistant", role="assistant", text="hi", timestamp="2026-05-22T08:14:11Z"),
    ]
    profiles = {
        42: _profile(preferred_name="Alice", timezone="Europe/Moscow"),
        99: _profile(preferred_name="Bob"),
    }
    content = SummarizerCore.build_context_message(chunk, [42], profiles)

    assert content.startswith("== PROFILES ==")
    assert "== CHUNK ==" in content
    assert '"user_id": 42' in content
    assert '"user_id": 99' not in content
    assert '"kind": "user"' in content
    assert '"user_id": 42' in content.split("== CHUNK ==")[1]
    assistant_line = [line for line in content.splitlines() if '"kind": "assistant"' in line][0]
    assert '"user_id"' not in assistant_line


# --- Stage 4: Validation and redaction ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("contact me@example.com", True),
        ("call +1-415-555-1234", True),
        ("password=secret123", True),
        ("sk-abc123token", True),
        ("Bearer eyJhbGciOiJIUzI1NiJ9", True),
        ("Berlin, Germany", False),
        ("software engineer", False),
        ("123 Main Street", True),
    ],
)
def test_is_redactable(text: str, expected: bool):
    assert SummarizerCore.is_redactable(text) is expected


def test_validate_envelope_happy_path():
    wire = LlmSummarizerEnvelope(
        summary="  User 42 moved.  ",
        topics=["move"],
        profile_updates={
            "42": {
                "location": "Berlin",
                "interests_to_add": ["hiking"],
                "skill_preferences_to_add": {
                    "web_search": ["weather: accuweather.com"],
                },
            },
        },
    )
    validated = SummarizerCore.validate_envelope(wire)
    assert validated.summary == "User 42 moved."
    assert validated.topics == ["move"]
    assert validated.profile_updates[42]["location"] == "Berlin"
    assert validated.profile_updates[42]["skill_preferences_to_add"] == {
        "search_web": ["weather: accuweather.com"],
    }


def test_validate_envelope_canonicalizes_dual_key_search_prefs():
    wire = LlmSummarizerEnvelope(
        summary="prefs",
        topics=[],
        profile_updates={
            "7": {
                "skill_preferences_to_add": {
                    "search_web": ["Prefer Reuters"],
                    "web_search": ["prefer reuters", "use AP"],
                    "schedule_message": ["short"],
                },
            },
        },
    )
    validated = SummarizerCore.validate_envelope(wire)
    prefs = validated.profile_updates[7]["skill_preferences_to_add"]
    assert prefs["search_web"] == ["Prefer Reuters", "use AP"]
    assert prefs["schedule_message"] == ["short"]
    assert "web_search" not in prefs


def test_validate_envelope_empty_profile_updates():
    wire = LlmSummarizerEnvelope(
        summary="summary text",
        topics=[],
        profile_updates={},
    )
    validated = SummarizerCore.validate_envelope(wire)
    assert validated.profile_updates == {}


def test_validate_envelope_topics_too_many():
    wire = LlmSummarizerEnvelope(
        summary="summary",
        topics=["a", "b", "c", "d", "e", "f"],
        profile_updates={},
    )
    with pytest.raises(SummarizerValidationError, match="topics"):
        SummarizerCore.validate_envelope(wire)


def test_validate_envelope_unknown_key():
    wire = LlmSummarizerEnvelope(
        summary="summary",
        topics=[],
        profile_updates={"42": {"unknown": "x"}},
    )
    with pytest.raises(SummarizerValidationError, match="unknown"):
        SummarizerCore.validate_envelope(wire)


def test_validate_envelope_non_numeric_user_key():
    wire = LlmSummarizerEnvelope(
        summary="summary",
        topics=[],
        profile_updates={"alice": {"location": "Berlin"}},
    )
    with pytest.raises(SummarizerValidationError, match="numeric"):
        SummarizerCore.validate_envelope(wire)


def test_validate_envelope_whitespace_scalar_dropped():
    wire = LlmSummarizerEnvelope(
        summary="summary",
        topics=[],
        profile_updates={"42": {"location": "   ", "occupation": "engineer"}},
    )
    validated = SummarizerCore.validate_envelope(wire)
    assert validated.profile_updates == {42: {"occupation": "engineer"}}


def test_validate_envelope_empty_user_dict_dropped():
    wire = LlmSummarizerEnvelope(
        summary="summary",
        topics=[],
        profile_updates={"42": {"location": "  "}},
    )
    validated = SummarizerCore.validate_envelope(wire)
    assert validated.profile_updates == {}


def test_redact_profile_updates_scalar_and_lists():
    updates = {
        42: {
            "location": "Berlin, Germany",
            "preferred_name": "alice@example.com",
            "facts_to_add": ["has a dog", "email me@bad.com"],
            "skill_preferences_to_add": {
                "web_search": ["safe pref", "password=secret"],
            },
        },
    }
    redacted = SummarizerCore.redact_profile_updates(updates)
    assert redacted == {
        42: {
            "location": "Berlin, Germany",
            "facts_to_add": ["has a dog"],
            "skill_preferences_to_add": {"search_web": ["safe pref"]},
        },
    }


def test_redact_profile_updates_omits_empty_user():
    updates = {42: {"preferred_name": "me@example.com"}}
    assert SummarizerCore.redact_profile_updates(updates) == {}


# --- Stage 5: Provider and fake LLM ---


@pytest.mark.asyncio
async def test_fake_llm_returns_parsed_envelope():
    fake = FakeLLMApi(
        responses=[
            json.dumps(
                {
                    "summary": "done",
                    "topics": [],
                    "profile_updates": {},
                },
            ),
        ],
    )
    result = await fake.parse_chat_async("model", [], LlmSummarizerEnvelope)
    assert isinstance(result, LlmSummarizerEnvelope)
    assert result.summary == "done"


@pytest.mark.asyncio
async def test_fake_llm_invalid_json_propagates():
    fake = FakeLLMApi(responses=["not json"])
    with pytest.raises(json.JSONDecodeError):
        await fake.parse_chat_async("model", [], LlmSummarizerEnvelope)


@pytest.mark.asyncio
async def test_summarise_happy_path():
    chunk = [
        _msg("user", user_id=42, text="hello"),
        _msg(
            "task_result",
            text="Tools used: web_search. Result: https://example.com",
        ),
    ]
    profiles = {42: _profile(preferred_name="Alice")}
    fake = FakeLLMApi(
        responses=[
            json.dumps(
                {
                    "summary": "User 42 said hello and searched the web.",
                    "topics": ["greeting"],
                    "profile_updates": {
                        "42": {
                            "occupation": "engineer",
                            "interests_to_add": ["hiking"],
                            "skill_preferences_to_add": {
                                "web_search": ["prefers example.com"],
                            },
                        },
                    },
                },
            ),
        ],
    )
    provider = SummarizerProvider(fake, SummarizerSettings(model_name="test-model"))
    result = await provider.summarise(chunk, profiles)

    assert result.summary == "User 42 said hello and searched the web."
    assert result.topics == ["greeting"]
    assert result.participants == [42]
    assert result.skills == ["web_search"]
    assert result.profile_updates[42]["occupation"] == "engineer"
    assert result.profile_updates[42]["skill_preferences_to_add"] == {
        "search_web": ["prefers example.com"],
    }

    _, messages, _ = fake.parse_calls[0]
    assert messages[0]["content"] == SUMMARIZER_SYSTEM_PROMPT
    assert "== PROFILES ==" in messages[1]["content"]
    assert "== CHUNK ==" in messages[1]["content"]


@pytest.mark.asyncio
async def test_summarise_missing_profile_raises():
    chunk = [_msg("user", user_id=42, text="hello")]
    fake = FakeLLMApi(responses=[])
    provider = SummarizerProvider(fake, SummarizerSettings(model_name="test-model"))
    with pytest.raises(ValueError, match="missing user ids"):
        await provider.summarise(chunk, {})


@pytest.mark.asyncio
async def test_summarise_validation_error_propagates(caplog):
    chunk = [_msg("user", user_id=42, text="hello")]
    profiles = {42: _profile()}
    fake = FakeLLMApi(
        responses=[
            json.dumps(
                {
                    "summary": "ok",
                    "topics": ["a", "b", "c", "d", "e", "f"],
                    "profile_updates": {},
                },
            ),
        ],
    )
    provider = SummarizerProvider(fake, SummarizerSettings(model_name="test-model"))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SummarizerValidationError):
            await provider.summarise(chunk, profiles)
    assert any("Summarizer validation failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_summarise_logging_success_debug_only(caplog):
    chunk = [_msg("user", user_id=42, text="hello")]
    profiles = {42: _profile()}
    response_json = json.dumps(
        {
            "summary": "summary text",
            "topics": [],
            "profile_updates": {},
        },
    )
    fake = FakeLLMApi(responses=[response_json, response_json])
    provider = SummarizerProvider(fake, SummarizerSettings(model_name="test-model"))
    with caplog.at_level(logging.INFO):
        await provider.summarise(chunk, profiles)
    assert not any("Summarizer success" in record.message for record in caplog.records)

    with caplog.at_level(logging.DEBUG):
        await provider.summarise(chunk, profiles)
    assert any("Summarizer success" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_summarise_empty_profile_updates_valid():
    chunk = [_msg("user", user_id=42, text="hello")]
    profiles = {42: _profile()}
    fake = FakeLLMApi(
        responses=[
            json.dumps(
                {
                    "summary": "summary text",
                    "topics": [],
                    "profile_updates": {},
                },
            ),
        ],
    )
    provider = SummarizerProvider(fake, SummarizerSettings(model_name="test-model"))
    result = await provider.summarise(chunk, profiles)
    assert result.profile_updates == {}


def test_summarizer_module_has_no_forbidden_imports():
    import yoda.mind.memory.summarizer as summarizer_module

    source = open(summarizer_module.__file__).read()
    for forbidden in ("MemoryProvider", "Mind", "Maintenance", "StorageApi"):
        assert forbidden not in source
