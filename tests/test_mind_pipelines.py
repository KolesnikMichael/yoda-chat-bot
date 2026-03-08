from pathlib import Path
from unittest.mock import patch

import pytest

from yoda.mind.affect import AffectProvider
from yoda.mind.mind import Mind
from yoda.mind.memory.memory import MemoryOperation
from yoda.mind.memory.data.conversation import Conversation


class FakeMemoryProvider:
  def __init__(self):
    self.sender_updates = []
    self.chat_updates = []
    self.conversations: dict[str, Conversation] = {}

  async def update_sender_info(self, user_id: int, chat_id: int, user_info: dict) -> None:
    self.sender_updates.append((user_id, chat_id, user_info))

  async def update_chat_info(self, chat_id: int, chat_type: str, last_active: str) -> None:
    self.chat_updates.append((chat_id, chat_type, last_active))

  def get_conversation(self, user_id: int, chat_id: int) -> Conversation | None:
    key = MemoryOperation.conversation_key(user_id, chat_id)
    return self.conversations.get(key)

  def save_conversation(self, conversation: Conversation) -> None:
    key = MemoryOperation.conversation_key(conversation.user_id, conversation.chat_id)
    self.conversations[key] = conversation


class FakeLanguageProvider:
  async def reply_in_conversation(self, conversation: list[dict]) -> str:
    return f"reply:{conversation[-1]['content']}"


class FakeAudioProvider:
  async def speech_to_text(self, audio_file_path, language: str = "ru-RU") -> str:
    return "voice text"


class FakeVisionProvider:
  async def image_to_description(self, image_file_path: str) -> str:
    return "a lightsaber in hand"


class FakeSender:
  def __init__(self):
    self.calls = []

  async def __call__(self, chat_id: int, message: str):
    self.calls.append((chat_id, message))


def build_mind(**overrides) -> Mind:
  defaults = dict(
      language_provider=FakeLanguageProvider(),
      vision_provider=FakeVisionProvider(),
      audio_provider=FakeAudioProvider(),
      memory_provider=FakeMemoryProvider(),
      affect_provider=AffectProvider(),
  )
  return Mind(**(defaults | overrides))


@pytest.mark.asyncio
async def test_text_pipeline_sends_response():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_text_message(
      user_id=1,
      chat_id=2,
      user_info={"last_active": "now"},
      message_text=" Hello ",
  )

  assert sender.calls == [(2, "reply:Hello")]
  conversation = memory_provider.get_conversation(user_id=1, chat_id=2)
  assert conversation is not None
  messages = conversation.to_llm_messages()
  assert messages[-2]["role"] == "user"
  assert messages[-1]["role"] == "assistant"


@pytest.mark.asyncio
@patch("yoda.mind.mind.AudioOperation.convert_ogg_to_wav", return_value=Path("voice.wav"))
async def test_voice_pipeline_uses_audio_provider(mock_convert_ogg_to_wav):
  sender = FakeSender()
  mind = build_mind()
  mind.bind_message_sender(sender)

  await mind.process_voice_message(
      user_id=7,
      chat_id=9,
      user_info={"last_active": "now"},
      audio_file_path="voice.ogg",
  )

  assert sender.calls == [(9, "reply:voice text")]


@pytest.mark.asyncio
async def test_photo_pipeline_adds_image_context():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_photo_message(
      user_id=3,
      chat_id=5,
      user_info={"last_active": "now"},
      photo_file_paths=["photo.jpg"],
      caption="What is this?",
  )

  conversation = memory_provider.get_conversation(user_id=3, chat_id=5)
  assert conversation is not None
  messages = conversation.to_llm_messages()
  system_lines = [m for m in messages if m["role"] == "system"]
  assert system_lines
  photo_line = next(m["content"] for m in system_lines if "image(s)" in m["content"])
  assert "a lightsaber in hand" in photo_line
  assert 'caption "What is this?"' in photo_line
  assert messages[-1]["role"] == "assistant"
  assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_photo_pipeline_combines_multiple_descriptions():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  call_count = 0

  class CountingVisionProvider:
    async def image_to_description(self, image_file_path: str) -> str:
      nonlocal call_count
      call_count += 1
      return f"description of {image_file_path}"

  mind = build_mind(
      memory_provider=memory_provider,
      vision_provider=CountingVisionProvider(),
  )
  mind.bind_message_sender(sender)

  await mind.process_photo_message(
      user_id=3,
      chat_id=5,
      user_info={"last_active": "now"},
      photo_file_paths=["photo1.jpg", "photo2.jpg", "photo3.jpg"],
      caption="What are these?",
  )

  assert call_count == 3
  conversation = memory_provider.get_conversation(user_id=3, chat_id=5)
  messages = conversation.to_llm_messages()
  system_lines = [m for m in messages if m["role"] == "system"]
  combined_line = next(m["content"] for m in system_lines if "image(s)" in m["content"])
  assert 'caption "What are these?"' in combined_line
  assert "[Photo 1]: description of photo1.jpg" in combined_line
  assert "[Photo 2]: description of photo2.jpg" in combined_line
  assert "[Photo 3]: description of photo3.jpg" in combined_line
  assert combined_line.count("\n") >= 3
  assert messages[-1]["role"] == "assistant"
  assert len(sender.calls) == 1
