from .memory.data.emotional_state import EmotionalState


class AffectOperation:
  @staticmethod
  def build_system_prompt(emotional_state: EmotionalState | None = None) -> str:
    # Keep behavior equivalent to current bot while leaving room for emotion-influenced prompts.
    return "Reply as Yoda from Star Wars"


class AffectProvider:
  def __init__(self, emotional_state: EmotionalState | None = None):
    self._emotional_state = emotional_state or EmotionalState()

  def get_emotional_state(self) -> EmotionalState:
    return self._emotional_state
