"""Shared test doubles for Mind pipeline tests."""

import json

from pydantic import BaseModel

from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.data.routing_context import RoutingContext
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.memory import MemoryCore


class FakeLLMApi:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.parse_calls: list[tuple[str, list[dict], type[BaseModel]]] = []

    async def parse_chat_async(
        self,
        model_name: str,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        self.parse_calls.append((model_name, messages, response_format))
        if not self._responses:
            raise RuntimeError("FakeLLMApi has no predetermined responses")
        raw = self._responses.pop(0)
        data = json.loads(raw)
        return response_format(**data)


class FakeMemoryProvider:
    def __init__(self) -> None:
        self.sender_updates: list[tuple] = []
        self.chat_updates: list[tuple] = []
        self._conversations: dict[str, Conversation] = {}

    async def update_sender_info(self, user_id: int, user_info: dict) -> None:
        self.sender_updates.append((user_id, user_info))

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

    async def append_conversation_line(
        self,
        conversation: Conversation | None,
        chat_id: int,
        *,
        kind,
        role: str,
        line: str,
        system_prompt: str = "Reply as Yoda from Star Wars",
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[Conversation, list[dict]]:
        profile_text: str | None = None
        introduced_users = conversation.introduced_users if conversation else set()
        needs_introduction = (
            kind == "user"
            and user_id is not None
            and user_id not in introduced_users
        )
        if needs_introduction:
            profile = await self.get_user_profile(user_id, chat_id)
            profile_text = MemoryCore.format_user_profile_snapshot(profile)

        conversation, _ = MemoryCore.add_conversation_line(
            conversation=conversation,
            chat_id=chat_id,
            kind=kind,
            role=role,
            line=line,
            system_prompt=system_prompt,
            timestamp=timestamp,
            message_id=message_id,
            user_id=user_id,
        )

        if needs_introduction and profile_text is not None and user_id is not None:
            user_index = len(conversation.messages) - 1
            MemoryCore.ensure_user_introductions_in_range(
                conversation,
                user_index,
                user_index + 1,
                lambda uid, text=profile_text: text,
            )

        return conversation, conversation.to_llm_messages()

    async def append_message(
        self,
        conversation: Conversation | None,
        chat_id: int,
        *,
        kind,
        role: str,
        line: str,
        system_prompt: str = "Reply as Yoda from Star Wars",
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[Conversation, list[dict]]:
        conversation, _ = MemoryCore.add_conversation_line(
            conversation=conversation,
            chat_id=chat_id,
            kind=kind,
            role=role,
            line=line,
            system_prompt=system_prompt,
            timestamp=timestamp,
            message_id=message_id,
            user_id=user_id,
        )
        return conversation, conversation.to_llm_messages()


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int | None]] = []

    async def __call__(
        self,
        chat_id: int,
        message: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> None:
        self.calls.append((chat_id, message, reply_to_message_id))


class FakeLanguageProvider:
    model_name = "test-model"

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

    async def classify_intent(self, routing: RoutingContext) -> str:
        return self._intent


class StubEmbeddingProvider:
    def __init__(self, *, fail: bool = False, dimension: int = 1536) -> None:
        self.fail = fail
        self._dimension = dimension
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return "openai/text-embedding-3-small"

    @property
    def vector_dimension(self) -> int:
        return self._dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("embed failed")
        return [[0.0] * self._dimension for _ in texts]

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]


class StubVectorProvider:
    def __init__(self) -> None:
        from yoda.mind.memory.vector import StoredSummaryRecord

        self._StoredSummaryRecord = StoredSummaryRecord
        self.records: dict[int, dict[str, object]] = {}
        self.persist_calls: list[tuple[int, int]] = []

    async def persist_summaries(self, chat_id: int, records: list) -> None:
        self.persist_calls.append((chat_id, len(records)))
        bucket = self.records.setdefault(chat_id, {})
        for record in records:
            bucket[record.summary_id] = self._StoredSummaryRecord(
                summary_id=record.summary_id,
                document=record.document,
                embedding=list(record.embedding),
            )

    async def list_stored_records(self, chat_id: int) -> list:
        bucket = self.records.get(chat_id, {})
        return list(bucket.values())

    async def delete_summary_ids(self, chat_id: int, ids: list[str]) -> None:
        bucket = self.records.get(chat_id)
        if not bucket:
            return
        for summary_id in ids:
            bucket.pop(summary_id, None)

    def list_chat_ids(self) -> list[int]:
        return sorted(self.records.keys())
