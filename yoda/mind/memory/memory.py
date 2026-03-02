import datetime as dtm
import json
import logging

from yoda.api.storage_api import StorageApi

from .data.conversation import Conversation
from .data.user_profile import UserProfile

logger = logging.getLogger(__name__)

CHAT_SCHEMA_VERSION = 2
DEFAULT_SYSTEM_PROMPT = "Reply as Yoda from Star Wars"


class MemoryOperation:
  @staticmethod
  def conversation_key(user_id: int, chat_id: int) -> str:
    return f"{user_id}@{chat_id}"

  @staticmethod
  def add_conversation_line(
      conversation: Conversation | None,
      user_id: int,
      chat_id: int,
      role: str = "user",
      line: str = "",
      system_prompt: str = DEFAULT_SYSTEM_PROMPT,
  ) -> tuple[Conversation, list[dict]]:
    if not conversation:
      key = MemoryOperation.conversation_key(user_id, chat_id)
      logger.info(f"Starting new conversation with {key}")
      conversation = Conversation(user_id=user_id, chat_id=chat_id)

    conversation.ensure_system_prompt(system_prompt)
    conversation.add_message(role=role, text=line)
    return conversation, conversation.to_llm_messages()


class MemoryProvider:
  def __init__(self, storage_api):
    self.storage_api = storage_api
    self.conversations: dict[str, Conversation] = {}

  @classmethod
  def from_settings(cls, memory_settings: dict) -> "MemoryProvider":
    storage_api = StorageApi(
        host=memory_settings.get("redis_host", "localhost"),
        port=memory_settings.get("redis_port", 6379),
        db=memory_settings.get("redis_db", 0),
    )
    return cls(storage_api=storage_api)

  def get_conversation(self, user_id: int, chat_id: int) -> Conversation | None:
    key = MemoryOperation.conversation_key(user_id, chat_id)
    return self.conversations.get(key)

  def save_conversation(self, conversation: Conversation) -> None:
    key = MemoryOperation.conversation_key(conversation.user_id, conversation.chat_id)
    self.conversations[key] = conversation

  async def update_sender_info(self, user_id: int, chat_id: int, user_info: dict) -> None:
    current_user_info_raw = await self.storage_api.hget("users", str(user_id))
    if current_user_info_raw:
      current_user_info = json.loads(current_user_info_raw)
    else:
      current_user_info = {"known_since": user_info.get("last_active")}
      logger.info(f"Registered user {user_id}")

    await self.storage_api.hset("users", str(user_id), json.dumps({**current_user_info, **user_info}))

    chat_type = "private" if user_id == chat_id else "group"
    await self.update_chat_info(
        chat_id=chat_id,
        chat_type=chat_type,
        last_active=user_info.get("last_active", ""),
    )

  async def update_chat_info(self, chat_id: int, chat_type: str, last_active: str) -> None:
    current_chat_info_raw = await self.storage_api.hget("chats", str(chat_id))
    if current_chat_info_raw:
      current_chat_info = json.loads(current_chat_info_raw)
      current_schema_version = current_chat_info.get("schema_version", 1)
      if current_schema_version < CHAT_SCHEMA_VERSION:
        current_chat_info = self._migrate_chat(current_chat_info, current_schema_version, chat_type)
    else:
      current_chat_info = {
          "chat_type": chat_type,
          "history": [],
          "conversation": {"users": [], "messages": []},
          "last_active": "",
          "schema_version": CHAT_SCHEMA_VERSION,
      }
      logger.info(f"Registered chat {chat_id}")

    current_chat_info["last_active"] = last_active
    await self.storage_api.hset("chats", str(chat_id), json.dumps(current_chat_info))

  async def update_user_profile(self, user_id: int, chat_id: int, user_profile: dict) -> None:
    user_profile_id = f"{user_id}@{chat_id}"
    current_user_profile_raw = await self.storage_api.hget("user_profiles", user_profile_id)

    if current_user_profile_raw:
      current_user_profile = json.loads(current_user_profile_raw)
    else:
      current_user_profile = UserProfile().__dict__

    current_user_profile = {**current_user_profile, **user_profile}
    current_user_profile["updated_on"] = dtm.datetime.now(dtm.UTC).isoformat()
    await self.storage_api.hset("user_profiles", user_profile_id, json.dumps(current_user_profile))

  def _migrate_chat(self, chat_info: dict, current_version: int, chat_type: str) -> dict:
    migrated = chat_info
    for version in range(current_version, CHAT_SCHEMA_VERSION):
      if version == 1:
        delta = {
            "chat_type": chat_type,
            "history": [],
            "conversation": {"users": [], "messages": []},
            "schema_version": version + 1,
        }
        migrated = {**migrated, **delta}
    return migrated
