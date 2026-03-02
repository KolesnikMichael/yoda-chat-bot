from .memory.data.emotion_state import EmotionState


class AffectOperation:
  @staticmethod
  def build_system_prompt(emotion_state: EmotionState | None = None) -> str:
    # Keep behavior equivalent to current bot while leaving room for emotion-influenced prompts.
    return "Reply as Yoda from Star Wars"


class AffectProvider:
  def __init__(self, emotion_state: EmotionState | None = None):
    self._emotion_state = emotion_state or EmotionState()

  def get_emotion_state(self) -> EmotionState:
    return self._emotion_state
