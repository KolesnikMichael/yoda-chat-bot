from .memory.data.emotional_state import EmotionalState
from .memory.data.system_prompt import DEFAULT_SYSTEM_PROMPT


class AffectCore:
    @staticmethod
    def build_system_prompt(
        emotional_state: EmotionalState | None = None,
        chat_type: str = "private",
        now: str = "",
    ) -> str:
        context_lines: list[str] = []

        if chat_type == "group":
            context_lines.append(
                "You are in a Telegram group chat. Multiple users may be present. "
                "Address users by name when relevant.")
        else:
            context_lines.append(
                "You are in a private Telegram chat, one-on-one.")

        context_lines.append(
            "Messages include timestamps. Use them for time-aware greetings "
            "and sensing conversation pace, but don't cite them explicitly unless relevant.")

        if now:
            context_lines.append(f"Current time: {now}")

        context_block = "\n== CONTEXT ==\n" + "\n".join(context_lines)
        return DEFAULT_SYSTEM_PROMPT.strip() + "\n" + context_block


class AffectProvider:
    def __init__(self, emotional_state: EmotionalState | None = None):
        self._emotional_state = emotional_state or EmotionalState()

    def get_emotional_state(self) -> EmotionalState:
        return self._emotional_state
