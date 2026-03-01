import json

import pytest

from yoda.mind.memory.memory import MemoryOperation


class FakeStorageApi:
  def __init__(self):
    self.data = {}

  async def hget(self, key: str, field: str):
    return self.data.get(key, {}).get(field)

  async def hset(self, key: str, field: str, value: str):
    bucket = self.data.setdefault(key, {})
    bucket[field] = value
    return 1


@pytest.mark.asyncio
async def test_update_sender_info_creates_user_and_chat():
  storage = FakeStorageApi()
  memory = MemoryOperation(storage_api=storage)
  user_info = {
      "username": "luke",
      "first_name": "Luke",
      "last_name": "Skywalker",
      "language_code": "en",
      "last_active": "2026-02-20T00:00:00",
  }

  await memory.update_sender_info(user_id=1, chat_id=1, user_info=user_info)

  saved_user = json.loads(storage.data["users"]["1"])
  saved_chat = json.loads(storage.data["chats"]["1"])
  assert saved_user["username"] == "luke"
  assert saved_user["known_since"] == "2026-02-20T00:00:00"
  assert saved_chat["chat_type"] == "private"
  assert saved_chat["schema_version"] == 2


def test_add_conversation_line_initializes_system_prompt():
  memory = MemoryOperation(storage_api=FakeStorageApi())

  messages = memory.add_conversation_line(
      user_id=9,
      chat_id=11,
      role="user",
      line="Hello there",
      system_prompt="Reply as Yoda from Star Wars",
  )

  assert messages[0] == {"role": "system", "content": "Reply as Yoda from Star Wars"}
  assert messages[1] == {"role": "user", "content": "Hello there"}
