from dataclasses import dataclass
from typing import Literal

MessageKind = Literal[
    "prompt",
    "user",
    "assistant",
    "task_result",
    "user_introduction",
    "summary",
]


@dataclass
class Message:
    role: str
    kind: MessageKind
    text: str = ""
    media_type: str = "text"
    timestamp: str = ""
    message_id: int | None = None
    user_id: int | None = None

    def to_llm_dict(self) -> dict:
        return {"role": self.role, "content": self.text}
