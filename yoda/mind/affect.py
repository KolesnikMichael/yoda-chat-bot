from .memory.data.emotional_state import EmotionalState
from .memory.data.system_prompt import DEFAULT_SYSTEM_PROMPT


class AffectCore:
    @staticmethod
    def build_system_prompt(
        emotional_state: EmotionalState | None = None,
        chat_type: str = "private",
    ) -> str:
        context_lines: list[str] = []

        if chat_type == "group":
            context_lines.append(
                "You are in a Telegram group chat. Multiple users may be present. "
                "Address users by name only when relevant. "
                "If you want your reply to appear as separate messages use $NEXT-MESSAGE$ as separator(s).")
        else:
            context_lines.append(
                "You are in a private Telegram chat, one-on-one. "
                "Call user by name only when you want to add some extra emphasis to your words.")

        context_lines.append(
            "Messages include timestamps. Treat the timestamp of the last message as the current time. "
            "Use timestamps for time-aware greetings and sensing conversation pace, "
            "but don't cite them explicitly unless relevant.")

        context_block = "\n== CONTEXT ==\n" + "\n".join(context_lines)
        return DEFAULT_SYSTEM_PROMPT.strip() + "\n" + context_block


class AffectProvider:
    def __init__(self, emotional_state: EmotionalState | None = None):
        self._emotional_state = emotional_state or EmotionalState()

    def get_emotional_state(self) -> EmotionalState:
        return self._emotional_state
