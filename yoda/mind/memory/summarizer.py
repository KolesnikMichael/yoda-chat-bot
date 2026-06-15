import json
import logging
import re
from dataclasses import dataclass

from yoda.api.llm_api import LLMApi
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.summarizer_envelope import (
    LlmSummarizerEnvelope,
    SummarizerValidationError,
)
from yoda.mind.memory.data.summarizer_prompt import SUMMARIZER_SYSTEM_PROMPT
from yoda.mind.memory.data.summarizer_result import SummarizerResult
from yoda.mind.memory.data.summarizer_settings import SummarizerSettings
from yoda.mind.memory.data.user_profile import UserProfile

logger = logging.getLogger(__name__)

SUMMARIZER_SCALAR_KEYS = frozenset({
    "preferred_name",
    "gender",
    "location",
    "timezone",
    "occupation",
})
SUMMARIZER_ALLOWED_USER_KEYS = SUMMARIZER_SCALAR_KEYS | frozenset({
    "interests_to_add",
    "facts_to_add",
    "skill_preferences_to_add",
})

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
)
_PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}(?:[-.\s]?\d{1,4})?",
)
_STREET_ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+\w+(?:\s+\w+){0,3}\s+"
    r"(?:street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|lane|ln\.?|drive|dr\.?)\b",
    re.IGNORECASE,
)
_IBAN_CARD_PATTERN = re.compile(
    r"\b(?:[A-Z]{2}\d{2}[A-Z0-9]{11,30}|\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})\b",
)
_SECRET_LITERAL_PATTERN = re.compile(
    r"(?i)(?:password|api_key|secret|sk-[a-zA-Z0-9]+|Bearer\s+\S+)",
)


@dataclass(frozen=True)
class ValidatedEnvelope:
    summary: str
    topics: list[str]
    profile_updates: dict[int, dict]


class SummarizerCore:
    @staticmethod
    def extract_participants(chunk: list[Message]) -> list[int]:
        return sorted({
            m.user_id
            for m in chunk
            if m.kind == "user" and m.user_id is not None
        })

    @staticmethod
    def extract_skills(chunk: list[Message]) -> list[str]:
        skills: set[str] = set()
        marker = "Tools used: "
        for message in chunk:
            if message.kind != "task_result" or marker not in message.text:
                continue
            start = message.text.index(marker) + len(marker)
            rest = message.text[start:]
            dot_index = rest.find(".")
            clause = rest[:dot_index] if dot_index != -1 else rest
            if clause == "none":
                continue
            for token in clause.split(", "):
                stripped = token.strip()
                if stripped:
                    skills.add(stripped)
        return sorted(skills)

    @staticmethod
    def build_context_message(
        chunk: list[Message],
        participants: list[int],
        participant_profiles: dict[int, UserProfile],
    ) -> str:
        lines = ["== PROFILES =="]
        for user_id in sorted(participants):
            profile = participant_profiles[user_id]
            profile_line = json.dumps(
                {"user_id": user_id, "profile": profile.to_dict()},
                ensure_ascii=False,
            )
            lines.append(profile_line)

        lines.append("")
        lines.append("== CHUNK ==")
        for message in chunk:
            record: dict[str, object] = {
                "kind": message.kind,
                "ts": message.timestamp,
                "content": message.text,
            }
            if message.kind == "user":
                record["user_id"] = message.user_id
            lines.append(json.dumps(record, ensure_ascii=False))

        return "\n".join(lines)

    @staticmethod
    def is_redactable(text: str) -> bool:
        if _EMAIL_PATTERN.search(text):
            return True
        if _PHONE_PATTERN.search(text) and sum(ch.isdigit() for ch in text) >= 7:
            return True
        if _STREET_ADDRESS_PATTERN.search(text):
            return True
        if _IBAN_CARD_PATTERN.search(text):
            return True
        if _SECRET_LITERAL_PATTERN.search(text):
            return True
        return False

    @staticmethod
    def validate_envelope(wire: LlmSummarizerEnvelope) -> ValidatedEnvelope:
        summary = wire.summary.strip()
        if not summary:
            raise SummarizerValidationError("summary must be non-empty")

        topics = wire.topics
        if len(topics) > 5:
            raise SummarizerValidationError("topics length must be at most 5")
        for topic in topics:
            if not isinstance(topic, str):
                raise SummarizerValidationError("each topic must be a string")

        profile_updates: dict[int, dict] = {}
        for user_key, user_delta in wire.profile_updates.items():
            try:
                user_id = int(user_key)
            except (TypeError, ValueError) as exc:
                raise SummarizerValidationError(
                    f"profile_updates key must be numeric: {user_key!r}",
                ) from exc

            if not isinstance(user_delta, dict):
                raise SummarizerValidationError(
                    f"profile_updates[{user_key!r}] must be an object",
                )

            normalised = SummarizerCore._normalise_user_delta(user_delta)
            if normalised:
                profile_updates[user_id] = normalised

        return ValidatedEnvelope(
            summary=summary,
            topics=topics,
            profile_updates=profile_updates,
        )

    @staticmethod
    def _normalise_user_delta(user_delta: dict[str, object]) -> dict:
        result: dict = {}
        for key, value in user_delta.items():
            if key not in SUMMARIZER_ALLOWED_USER_KEYS:
                raise SummarizerValidationError(f"unknown profile_updates key: {key!r}")

            if key in SUMMARIZER_SCALAR_KEYS:
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise SummarizerValidationError(
                        f"{key} must be a string, got {type(value).__name__}",
                    )
                if not value.strip():
                    continue
                result[key] = value.strip()
                continue

            if key in ("interests_to_add", "facts_to_add"):
                if not isinstance(value, list):
                    raise SummarizerValidationError(
                        f"{key} must be a list, got {type(value).__name__}",
                    )
                items = []
                for item in value:
                    if not isinstance(item, str) or not item.strip():
                        raise SummarizerValidationError(
                            f"{key} items must be non-empty strings",
                        )
                    items.append(item.strip())
                if items:
                    result[key] = items
                continue

            if key == "skill_preferences_to_add":
                if not isinstance(value, dict):
                    raise SummarizerValidationError(
                        "skill_preferences_to_add must be a dict",
                    )
                preferences: dict[str, list[str]] = {}
                for skill_name, pref_list in value.items():
                    if not isinstance(skill_name, str) or not skill_name.strip():
                        raise SummarizerValidationError(
                            "skill_preferences_to_add keys must be non-empty strings",
                        )
                    if not isinstance(pref_list, list):
                        raise SummarizerValidationError(
                            "skill_preferences_to_add values must be lists",
                        )
                    cleaned_prefs = []
                    for pref in pref_list:
                        if not isinstance(pref, str) or not pref.strip():
                            raise SummarizerValidationError(
                                "skill_preferences_to_add items must be non-empty strings",
                            )
                        cleaned_prefs.append(pref.strip())
                    if cleaned_prefs:
                        preferences[skill_name.strip()] = cleaned_prefs
                if preferences:
                    result[key] = preferences

        return result

    @staticmethod
    def redact_profile_updates(updates: dict[int, dict]) -> dict[int, dict]:
        result: dict[int, dict] = {}
        for user_id, user_delta in updates.items():
            redacted = SummarizerCore._redact_user_delta(user_delta)
            if redacted:
                result[user_id] = redacted
        return result

    @staticmethod
    def _redact_user_delta(user_delta: dict) -> dict:
        result: dict = {}
        for key, value in user_delta.items():
            if key in SUMMARIZER_SCALAR_KEYS:
                if isinstance(value, str) and not SummarizerCore.is_redactable(value):
                    result[key] = value
                continue

            if key in ("interests_to_add", "facts_to_add"):
                if isinstance(value, list):
                    kept = [
                        item
                        for item in value
                        if isinstance(item, str) and not SummarizerCore.is_redactable(item)
                    ]
                    if kept:
                        result[key] = kept
                continue

            if key == "skill_preferences_to_add" and isinstance(value, dict):
                preferences: dict[str, list[str]] = {}
                for skill_name, pref_list in value.items():
                    if not isinstance(pref_list, list):
                        continue
                    kept_prefs = [
                        pref
                        for pref in pref_list
                        if isinstance(pref, str) and not SummarizerCore.is_redactable(pref)
                    ]
                    if kept_prefs:
                        preferences[skill_name] = kept_prefs
                if preferences:
                    result[key] = preferences

        return result


class SummarizerProvider:
    def __init__(self, llm_api: LLMApi, settings: SummarizerSettings) -> None:
        self._llm_api = llm_api
        self._settings = settings

    async def summarise(
        self,
        chunk: list[Message],
        participant_profiles: dict[int, UserProfile],
    ) -> SummarizerResult:
        participants = SummarizerCore.extract_participants(chunk)
        missing = [user_id for user_id in participants if user_id not in participant_profiles]
        if missing:
            raise ValueError(
                f"participant_profiles missing user ids: {sorted(missing)}",
            )

        user_content = SummarizerCore.build_context_message(
            chunk,
            participants,
            participant_profiles,
        )
        messages = [
            {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            wire = await self._llm_api.parse_chat_async(
                self._settings.model_name,
                messages,
                LlmSummarizerEnvelope,
            )
            envelope = SummarizerCore.validate_envelope(wire)
        except SummarizerValidationError as exc:
            logger.error("Summarizer validation failed: %s", exc)
            raise

        profile_updates = SummarizerCore.redact_profile_updates(envelope.profile_updates)
        skills = SummarizerCore.extract_skills(chunk)

        logger.debug(
            "Summarizer success: summary_len=%d participants=%d skills=%d profile_updates=%d",
            len(envelope.summary),
            len(participants),
            len(skills),
            len(profile_updates),
        )

        return SummarizerResult(
            summary=envelope.summary,
            topics=envelope.topics,
            participants=participants,
            skills=skills,
            profile_updates=profile_updates,
        )
