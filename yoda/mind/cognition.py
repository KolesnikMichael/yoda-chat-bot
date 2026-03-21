from pydantic import BaseModel

INTENT_CLASSIFICATION_PROMPT = (
    "Classify the user's message intent. "
    "Respond with a JSON object: {\"intent\": \"agent_task\"} or {\"intent\": \"chat\"}.\n"
    "- \"agent_task\": user requests an action that requires tools "
    "(scheduling reminders, searching the web, setting timers, etc.)\n"
    "- \"chat\": everything else (conversation, questions, greetings, opinions)\n"
)


class IntentClassification(BaseModel):
    intent: str


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
    def build_intent_messages(user_text: str) -> list[dict]:
        return [
            {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": user_text},
        ]

    @staticmethod
    def extract_user_text(perceived_entries: list[dict]) -> str:
        """Extract the last meaningful user text from perceived entries."""
        for entry in reversed(perceived_entries):
            text = entry.get("text", "")
            if "sent text message:" in text or "sent voice message:" in text:
                start = text.find('"')
                end = text.rfind('"')
                if start != -1 and end > start:
                    return text[start + 1:end]
        return ""
