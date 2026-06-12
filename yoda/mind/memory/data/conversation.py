from dataclasses import dataclass, field

from .message import Message, MessageKind
from .summary_outbox_entry import SummaryOutboxEntry


@dataclass
class Conversation:
    chat_id: int
    messages: list[Message] = field(default_factory=list)
    last_visible_at: float = 0.0
    last_compressed_at: float = 0.0
    visible_messages: int = 0
    introduced_users: set[int] = field(default_factory=set)
    pending_vectorization: list[SummaryOutboxEntry] = field(default_factory=list)

    def ensure_system_prompt(self, system_prompt: str) -> None:
        if not self.messages:
            self.messages.append(
                Message(role="system", kind="prompt", text=system_prompt)
            )

    def add_message(
        self,
        *,
        kind: MessageKind,
        role: str,
        text: str,
        media_type: str = "text",
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> None:
        self.messages.append(
            Message(
                role=role,
                kind=kind,
                text=text,
                media_type=media_type,
                timestamp=timestamp,
                message_id=message_id,
                user_id=user_id,
            )
        )

    def to_llm_messages(self) -> list[dict]:
        return [message.to_llm_dict() for message in self.messages]
