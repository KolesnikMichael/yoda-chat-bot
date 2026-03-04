from dataclasses import dataclass, field

from .message import Message


@dataclass
class Conversation:
  user_id: int
  chat_id: int
  messages: list[Message] = field(default_factory=list)

  def ensure_system_prompt(self, system_prompt: str) -> None:
    if not self.messages:
      self.messages.append(Message(role="system", text=system_prompt))

  def add_message(self, role: str, text: str, media_type: str = "text", timestamp: str = "") -> None:
    self.messages.append(
        Message(
            role=role,
            text=text,
            media_type=media_type,
            timestamp=timestamp,
        )
    )

  def to_llm_messages(self) -> list[dict]:
    return [message.to_llm_dict() for message in self.messages]
