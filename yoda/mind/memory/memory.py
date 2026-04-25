import datetime as dtm
import json
import logging
from dataclasses import asdict

from .data.chat import Chat
from .data.conversation import Conversation
from .data.message import Message
from .data.system_prompt import DEFAULT_SYSTEM_PROMPT
from .data.user import User
from .data.user_profile import UserProfile
from .migration import migrate

logger = logging.getLogger(__name__)

# Ephemeral Redis STRING: written on graceful shutdown, consumed and deleted on next startup.
CONVERSATION_STASH_REDIS_KEY = "conversation_stash"
CONVERSATION_STASH_SCHEMA_VERSION = 2


class MemoryCore:
    @staticmethod
    def conversation_key(chat_id: int) -> str:
        return str(chat_id)

    @staticmethod
    def add_conversation_line(
        conversation: Conversation | None,
        chat_id: int,
        role: str,
        line: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[Conversation, list[dict]]:
        if not conversation:
            key = MemoryCore.conversation_key(chat_id)
            logger.info(f"Starting new conversation in chat {key}")
            conversation = Conversation(chat_id=chat_id)

        conversation.ensure_system_prompt(system_prompt)
        conversation.add_message(
            role=role,
            text=line,
            timestamp=timestamp,
            message_id=message_id,
            user_id=user_id,
        )
        return conversation, conversation.to_llm_messages()

    @staticmethod
    def conversations_to_stash_dict(conversations: dict[str, Conversation]) -> dict:
        wire_conversations: dict[str, dict] = {}
        for key, conv in conversations.items():
            wire_conversations[key] = {
                "chat_id": conv.chat_id,
                "messages": [asdict(m) for m in conv.messages],
            }
        return {
            "schema_version": CONVERSATION_STASH_SCHEMA_VERSION,
            "conversations": wire_conversations,
        }

    @staticmethod
    def stash_dict_to_conversations(data: dict) -> dict[str, Conversation]:
        raw = data.get("conversations", {})
        if not isinstance(raw, dict):
            return {}
        out: dict[str, Conversation] = {}
        for payload in raw.values():
            if not isinstance(payload, dict):
                continue
            chat_id = int(payload["chat_id"])
            messages = [
                Message(**{k: v for k, v in msg.items()
                           if k in Message.__dataclass_fields__})
                for msg in payload.get("messages", [])
                if isinstance(msg, dict)
            ]
            out[MemoryCore.conversation_key(chat_id)] = Conversation(
                chat_id=chat_id, messages=messages
            )
        return out


class MemoryProvider:
    def __init__(self, storage_api):
        self._storage_api = storage_api
        self._conversations: dict[str, Conversation] = {}

    def get_conversation(self, chat_id: int) -> Conversation | None:
        key = MemoryCore.conversation_key(chat_id)
        return self._conversations.get(key)

    def save_conversation(self, conversation: Conversation) -> None:
        key = MemoryCore.conversation_key(conversation.chat_id)
        self._conversations[key] = conversation

    def forget_conversation(self, chat_id: int) -> None:
        key = MemoryCore.conversation_key(chat_id)
        self._conversations.pop(key, None)

    async def save_conversation_stash(self) -> None:
        if not self._conversations:
            await self._storage_api.delete(CONVERSATION_STASH_REDIS_KEY)
            logger.info("Conversation stash: no conversations to save, key removed")
            return
        payload = MemoryCore.conversations_to_stash_dict(self._conversations)
        raw = json.dumps(payload)
        await self._storage_api.set(CONVERSATION_STASH_REDIS_KEY, raw)
        logger.info(f"Conversation stash: saved {len(self._conversations)} chat(s) to Redis")

    async def restore_conversation_stash(self) -> None:
        raw = await self._storage_api.get(CONVERSATION_STASH_REDIS_KEY)
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.exception("Conversation stash: invalid JSON, key left in place")
            return
        if not isinstance(data, dict):
            logger.error("Conversation stash: root must be an object, key left in place")
            return
        try:
            data = migrate("conversation_stash", data)
            restored = MemoryCore.stash_dict_to_conversations(data)
        except Exception:
            logger.exception(
                "Conversation stash: restore failed, key left in place for inspection"
            )
            return
        self._conversations = restored
        await self._storage_api.delete(CONVERSATION_STASH_REDIS_KEY)
        logger.info(f"Conversation stash: restored {len(restored)} chat(s), key removed")

    async def update_sender_info(self, user_id: int, user_info: dict) -> None:
        raw = await self._storage_api.hget("users", str(user_id))
        if raw:
            data = migrate("users", json.loads(raw))
            user = User(**{k: v for k, v in data.items() if k in User.__dataclass_fields__})
        else:
            user = User(known_since=user_info.get("last_active", ""))
            logger.info(f"Registered user {user_id}")

        for field in ("username", "first_name", "last_name", "last_active"):
            if field in user_info:
                setattr(user, field, user_info[field])

        await self._storage_api.hset("users", str(user_id), json.dumps(user.to_dict()))

    async def update_chat_info(self, chat_id: int, chat_type: str, last_active: str) -> None:
        raw = await self._storage_api.hget("chats", str(chat_id))
        if raw:
            data = migrate("chats", json.loads(raw))
            chat = Chat(**{k: v for k, v in data.items() if k in Chat.__dataclass_fields__})
        else:
            chat = Chat(chat_type=chat_type)
            logger.info(f"Registered chat {chat_id}")

        chat.last_active = last_active
        chat.updated_on = dtm.datetime.now(dtm.UTC).isoformat()
        await self._storage_api.hset("chats", str(chat_id), json.dumps(chat.to_dict()))

    async def get_user_profile(self, user_id: int, chat_id: int) -> UserProfile:
        user_profile_id = f"{user_id}@{chat_id}"
        raw = await self._storage_api.hget("user_profiles", user_profile_id)
        if raw:
            data = migrate("user_profiles", json.loads(raw))
            return UserProfile(
                **{k: v for k, v in data.items() if k in UserProfile.__dataclass_fields__}
            )
        return UserProfile()

    async def update_user_profile(self, user_id: int, chat_id: int, user_profile: dict) -> None:
        user_profile_id = f"{user_id}@{chat_id}"
        raw = await self._storage_api.hget("user_profiles", user_profile_id)

        if raw:
            data = migrate("user_profiles", json.loads(raw))
            current = UserProfile(
                **{k: v for k, v in data.items() if k in UserProfile.__dataclass_fields__}
            )
        else:
            current = UserProfile()

        for k, v in user_profile.items():
            if k in UserProfile.__dataclass_fields__:
                setattr(current, k, v)

        current.updated_on = dtm.datetime.now(dtm.UTC).isoformat()
        await self._storage_api.hset("user_profiles", user_profile_id, json.dumps(current.to_dict()))
