from dataclasses import dataclass


@dataclass
class Message:
    role: str
    text: str = ""
    media_type: str = "text"
    timestamp: str = ""
    message_id: int | None = None
    user_id: int | None = None

    def to_llm_dict(self) -> dict:
        return {"role": self.role, "content": self.text}
