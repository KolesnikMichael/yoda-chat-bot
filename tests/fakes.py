"""Shared test doubles for Mind pipeline tests."""

from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.memory import MemoryCore


class FakeMemoryProvider:
    def __init__(self) -> None:
        self.sender_updates: list[tuple] = []
        self.chat_updates: list[tuple] = []
        self._conversations: dict[str, Conversation] = {}

    async def update_sender_info(self, user_id: int, chat_id: int, user_info: dict) -> None:
        self.sender_updates.append((user_id, chat_id, user_info))

    async def update_chat_info(self, chat_id: int, chat_type: str, last_active: str) -> None:
        self.chat_updates.append((chat_id, chat_type, last_active))

    def get_conversation(self, chat_id: int) -> Conversation | None:
        key = MemoryCore.conversation_key(chat_id)
        return self._conversations.get(key)

    def save_conversation(self, conversation: Conversation) -> None:
        key = MemoryCore.conversation_key(conversation.chat_id)
        self._conversations[key] = conversation

    async def get_user_profile(self, user_id: int, chat_id: int) -> UserProfile:
        return UserProfile(timezone="Europe/Moscow")


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def __call__(self, chat_id: int, message: str) -> None:
        self.calls.append((chat_id, message))


class FakeLanguageProvider:
    def __init__(self) -> None:
        self.reply_calls: list[list[dict]] = []

    async def reply_in_conversation(self, conversation: list[dict]) -> str:
        self.reply_calls.append(conversation)
        return f"reply:{conversation[-1]['content']}"


class FakeAudioProvider:
    async def speech_to_text(self, audio_file_path, language: str = "ru-RU") -> str:
        return "voice text"


class FakeVisionProvider:
    async def image_to_description(self, image_file_path: str) -> str:
        return "a lightsaber in hand"


class FakeCognitionProvider:
    def __init__(self, intent: str = "chat") -> None:
        self._intent = intent

    async def classify_intent(self, user_text: str) -> str:
        return self._intent
