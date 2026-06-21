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
        if self.kind == "summary":
            from .inline_summary_envelope import InlineSummaryEnvelope

            content = InlineSummaryEnvelope.from_message_text(self.text).to_llm_content()
            return {"role": self.role, "content": content}
        return {"role": self.role, "content": self.text}
