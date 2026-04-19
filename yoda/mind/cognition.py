import logging
from typing import TypedDict

from pydantic import BaseModel

from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.routing_context import (
    RoutingContext,
    format_recent_messages_block,
)
from yoda.mind.perception.language import LanguageProvider

logger = logging.getLogger(__name__)

INTENT_CLASSIFICATION_PROMPT = (
    "Classify the user's intent from one or more messages. "
    "You may receive a short \"Recent conversation\" excerpt before the current user message. "
    "Use it when the latest message is only a refinement (e.g. different time, extra constraint) "
    "or a repeat of a prior tool/skill request with different parameters — "
    "those still count as agent_task if tools/skills are needed.\n"
    "Respond with a JSON object: {\"intent\": \"agent_task\"} or {\"intent\": \"chat\"}.\n"
    "- \"agent_task\": user requests an action that requires tools "
    "(scheduling reminders, searching the web, setting timers, etc.)\n"
    "- \"chat\": everything else (conversation, questions, greetings, opinions)\n"
)


class IntentClassification(BaseModel):
    intent: str


class ReplyDeliveryPart(TypedDict):
    text: str
    message_id: int | None


class CognitionCore:
    @staticmethod
    def normalize_user_text(text: str) -> str:
        normalized = (text or "").strip()
        return normalized if normalized else "<got empty message from user>"

    @staticmethod
    def determine_chat_type(user_id: int, chat_id: int) -> str:
        return "private" if user_id == chat_id else "group"

    @staticmethod
    def should_reply(chat_type: str) -> bool:
        return True

    @staticmethod
    def process_reply(reply: str) -> list[ReplyDeliveryPart]:
        """Split reply into chat sends; parse markers / reply targets (stub)."""
        return [{"text": reply, "message_id": None}]

    @staticmethod
    def build_intent_context_messages(
        conversation: Conversation | None,
        *,
        limit: int = 4,
        exclude_trailing: int = 0,
    ) -> list[dict]:
        if not conversation or not conversation.messages:
            return []
        msgs = list(conversation.messages[1:])
        if exclude_trailing > 0:
            if len(msgs) <= exclude_trailing:
                return []
            msgs = msgs[:-exclude_trailing]
        if not msgs:
            return []
        tail = msgs[-limit:]
        return [m.to_llm_dict() for m in tail]

    @staticmethod
    def build_routing_context(
        perceived: list[dict],
        conversation: Conversation | None,
    ) -> RoutingContext:
        return RoutingContext(
            current_user_text=CognitionCore.extract_user_text(perceived),
            recent_messages=CognitionCore.build_intent_context_messages(
                conversation,
                exclude_trailing=len(perceived),
            ),
        )

    @staticmethod
    def build_intent_messages(
        user_text: str, recent_messages: list[dict] | None = None
    ) -> list[dict]:
        out: list[dict] = [
            {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
        ]
        if recent_messages:
            block = format_recent_messages_block(recent_messages)
            if block:
                out.append({"role": "user", "content": block})
        out.append({"role": "user", "content": user_text})
        return out

    @staticmethod
    def build_intent_messages_from_routing(routing: RoutingContext) -> list[dict]:
        return CognitionCore.build_intent_messages(
            routing.current_user_text,
            recent_messages=routing.recent_messages or None,
        )

    @staticmethod
    def extract_user_text(perceived_entries: list[dict]) -> str:
        """Extract user-authored text from all perceived entries in batch order."""
        parts: list[str] = []
        for entry in perceived_entries:
            line = entry.get("text", "")
            chunk = CognitionCore._user_text_from_perceived_line(line)
            if chunk:
                parts.append(chunk)
        return "\n".join(parts)

    @staticmethod
    def _user_text_from_perceived_line(line: str) -> str:
        if not line:
            return ""
        if "sent text message:" in line or "sent voice message:" in line:
            start = line.find('"')
            end = line.rfind('"')
            if start != -1 and end > start:
                return line[start + 1:end]
            return ""
        if 'with caption "' in line:
            prefix = 'with caption "'
            i = line.find(prefix)
            if i != -1:
                start = i + len(prefix)
                end = line.find('"', start)
                if end != -1:
                    return line[start:end]
        return ""


class CognitionProvider:
    """Provider (async): LLM-based intent classification for agent routing."""

    def __init__(self, language_provider: LanguageProvider):
        self._llm = language_provider

    async def classify_intent(self, routing: RoutingContext) -> str:
        intent_messages = CognitionCore.build_intent_messages_from_routing(routing)
        result = await self._llm.parse_structured(
            intent_messages, IntentClassification)
        logger.debug(
            f"Intent classification: '{routing.current_user_text[:80]}' -> "
            f"{result.intent}")
        if result.intent in ("agent_task", "chat"):
            return result.intent
        return "pass"
