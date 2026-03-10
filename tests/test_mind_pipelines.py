from pathlib import Path
from unittest.mock import patch

import pytest

from yoda.mind.affect import AffectProvider
from yoda.mind.mind import Mind
from yoda.mind.memory.memory import MemoryOperation
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.pending_message import PendingMessage


class FakeMemoryProvider:
  def __init__(self):
    self.sender_updates = []
    self.chat_updates = []
    self.conversations: dict[str, Conversation] = {}

  async def update_sender_info(self, user_id: int, chat_id: int, user_info: dict) -> None:
    self.sender_updates.append((user_id, chat_id, user_info))

  async def update_chat_info(self, chat_id: int, chat_type: str, last_active: str) -> None:
    self.chat_updates.append((chat_id, chat_type, last_active))

  def get_conversation(self, chat_id: int) -> Conversation | None:
    key = MemoryOperation.conversation_key(chat_id)
    return self.conversations.get(key)

  def save_conversation(self, conversation: Conversation) -> None:
    key = MemoryOperation.conversation_key(conversation.chat_id)
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


def make_pending(media_type: str = "text", text: str = "Hello",
                 user_id: int = 1, first_name: str = "Luke",
                 photo_file_paths: list[str] | None = None,
                 caption: str = "", audio_file_path: str = "",
                 media_group_id: str | None = None,
                 timestamp: str = "2026-03-09 21:36:51+00:00") -> PendingMessage:
  return PendingMessage(
      user_id=user_id,
      user_info={"first_name": first_name, "last_active": "now"},
      media_type=media_type,
      text=text,
      photo_file_paths=photo_file_paths or [],
      caption=caption,
      audio_file_path=audio_file_path,
      media_group_id=media_group_id,
      timestamp=timestamp,
  )


@pytest.mark.asyncio
async def test_text_batch_sends_response():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_message_batch(
      chat_id=1,
      batch=[make_pending(text=" Hello ", user_id=1)],
  )

  assert sender.calls == [
      (1, "reply:On 2026-03-09 21:36:51+00:00 Luke: Hello")
  ]
  conversation = memory_provider.get_conversation(chat_id=1)
  assert conversation is not None
  messages = conversation.to_llm_messages()
  assert messages[-2]["role"] == "system"
  assert messages[-1]["role"] == "assistant"


@pytest.mark.asyncio
@patch("yoda.mind.mind.AudioOperation.convert_ogg_to_wav", return_value=Path("voice.wav"))
async def test_voice_batch_uses_audio_provider(mock_convert):
  sender = FakeSender()
  mind = build_mind()
  mind.bind_message_sender(sender)

  await mind.process_message_batch(
      chat_id=7,
      batch=[make_pending(media_type="voice", audio_file_path="voice.ogg", user_id=7)],
  )

  assert sender.calls == [(7, "reply:On Luke (voice): voice text")]


@pytest.mark.asyncio
async def test_photo_batch_adds_image_context():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_message_batch(
      chat_id=5,
      batch=[make_pending(
          media_type="photo", user_id=5,
          photo_file_paths=["photo.jpg"], caption="What is this?",
      )],
  )

  conversation = memory_provider.get_conversation(chat_id=5)
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
async def test_photo_batch_combines_multiple_descriptions():
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

  await mind.process_message_batch(
      chat_id=5,
      batch=[make_pending(
          media_type="photo", user_id=5,
          photo_file_paths=["photo1.jpg", "photo2.jpg", "photo3.jpg"],
          caption="What are these?",
      )],
  )

  assert call_count == 3
  conversation = memory_provider.get_conversation(chat_id=5)
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


@pytest.mark.asyncio
@patch("yoda.mind.mind.AudioOperation.convert_ogg_to_wav", return_value=Path("voice.wav"))
async def test_mixed_batch_processes_all_types(mock_convert):
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_message_batch(
      chat_id=1,
      batch=[
          make_pending(text="hey", user_id=1),
          make_pending(media_type="photo", user_id=1,
                       photo_file_paths=["pic.jpg"], caption="look"),
          make_pending(media_type="voice", user_id=1, audio_file_path="v.ogg"),
      ],
  )

  conversation = memory_provider.get_conversation(chat_id=1)
  messages = conversation.to_llm_messages()
  roles = [m["role"] for m in messages]
  assert roles.count("system") >= 2
  assert roles[-1] == "assistant"
  assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_group_chat_text_includes_sender_name():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_message_batch(
      chat_id=100,
      batch=[
          make_pending(text="hello", user_id=42, first_name="Obi"),
          make_pending(text="hi there", user_id=43, first_name="Anakin"),
      ],
  )

  conversation = memory_provider.get_conversation(chat_id=100)
  messages = conversation.to_llm_messages()
  system_messages = [m["content"] for m in messages if m["role"] == "system"]
  assert "On 2026-03-09 21:36:51+00:00 Obi: hello" in system_messages
  assert "On 2026-03-09 21:36:51+00:00 Anakin: hi there" in system_messages


@pytest.mark.asyncio
async def test_timestamps_stored_on_messages():
  memory_provider = FakeMemoryProvider()
  sender = FakeSender()
  mind = build_mind(memory_provider=memory_provider)
  mind.bind_message_sender(sender)

  await mind.process_message_batch(
      chat_id=1,
      batch=[make_pending(text="Hi", user_id=1, timestamp="2026-03-09 21:36:51+00:00")],
  )

  conversation = memory_provider.get_conversation(chat_id=1)
  incoming_msg = next(m for m in conversation.messages if "Hi" in m.text)
  assert incoming_msg.timestamp == "2026-03-09 21:36:51+00:00"
  assistant_msg = next(m for m in conversation.messages if m.role == "assistant")
  assert assistant_msg.timestamp != ""


@pytest.mark.asyncio
async def test_empty_batch_is_noop():
  sender = FakeSender()
  mind = build_mind()
  mind.bind_message_sender(sender)

  await mind.process_message_batch(chat_id=1, batch=[])

  assert sender.calls == []
