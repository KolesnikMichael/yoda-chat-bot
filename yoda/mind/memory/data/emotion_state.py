from dataclasses import dataclass


@dataclass
class EmotionState:
  glad: float = 0.0
  mad: float = 0.0
  sad: float = 0.0
  scared: float = 0.0
