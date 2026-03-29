from pydantic import BaseModel

INTENT_CLASSIFICATION_PROMPT = (
    "Classify the user's intent from one or more messages. "
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
