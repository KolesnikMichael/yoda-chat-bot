import pytest

from yoda.mind.mind import Mind


class FakeMemoryOperation:
  def __init__(self):
    self.sender_updates = []
    self.lines = []

  async def update_sender_info(self, user_id: int, chat_id: int, user_info: dict) -> None:
    self.sender_updates.append((user_id, chat_id, user_info))

  def add_conversation_line(self, user_id: int, chat_id: int, role: str, line: str, system_prompt: str) -> list[dict]:
    self.lines.append(
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "role": role,
            "line": line,
            "system_prompt": system_prompt,
        }
    )
    return [{"role": "system", "content": system_prompt}, {"role": role, "content": line}]


class FakeLanguageProvider:
  async def reply_in_conversation(self, conversation: list[dict]) -> str:
    return f"reply:{conversation[-1]['content']}"


class FakeAudioProvider:
  async def speech_to_text(self, audio_file_path, language: str = "ru-RU") -> str:
    return "voice text"


class FakeVisionProvider:
  async def image_to_description(self, image_file_path: str) -> str:
    return "a lightsaber in hand"


class FakeCognitionOperation:
  def normalize_user_text(self, text: str) -> str:
    return text.strip()


class FakeAffectOperation:
  def build_system_prompt(self) -> str:
    return "Reply as Yoda from Star Wars"


class FakeSender:
  def __init__(self):
    self.calls = []

  async def __call__(self, chat_id: int, message: str):
    self.calls.append((chat_id, message))


def build_settings():
  return {
      "reason": {
          "intelligence": {
              "language_processing": {"mistral_large_latest": {"model_name": "mistral-large-latest", "api_key": "x"}},
              "computer_vision": {"pixtral_large_latest": {"model_name": "pixtral-large-latest", "api_key": "x"}},
          }
      },
      "memory": {},
      "emotions": {"glad": 0, "mad": 0, "sad": 0, "scared": 0},
  }


@pytest.mark.asyncio
async def test_text_pipeline_sends_response():
  memory = FakeMemoryOperation()
  sender = FakeSender()
  mind = Mind(
      build_settings(),
      memory_operation=memory,
      cognition_operation=FakeCognitionOperation(),
      affect_operation=FakeAffectOperation(),
      language_provider=FakeLanguageProvider(),
      audio_provider=FakeAudioProvider(),
      vision_provider=FakeVisionProvider(),
  )
  mind.bind_message_sender(sender)

  await mind.process_text_message(
      user_id=1,
      chat_id=2,
      user_info={"last_active": "now"},
      message_text=" Hello ",
  )

  assert sender.calls == [(2, "reply:Hello")]
  assert memory.lines[0]["role"] == "user"
  assert memory.lines[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_voice_pipeline_uses_audio_provider():
  memory = FakeMemoryOperation()
  sender = FakeSender()
  mind = Mind(
      build_settings(),
      memory_operation=memory,
      cognition_operation=FakeCognitionOperation(),
      affect_operation=FakeAffectOperation(),
      language_provider=FakeLanguageProvider(),
      audio_provider=FakeAudioProvider(),
      vision_provider=FakeVisionProvider(),
  )
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
  memory = FakeMemoryOperation()
  sender = FakeSender()
  mind = Mind(
      build_settings(),
      memory_operation=memory,
      cognition_operation=FakeCognitionOperation(),
      affect_operation=FakeAffectOperation(),
      language_provider=FakeLanguageProvider(),
      audio_provider=FakeAudioProvider(),
      vision_provider=FakeVisionProvider(),
  )
  mind.bind_message_sender(sender)

  await mind.process_photo_message(
      user_id=3,
      chat_id=5,
      user_info={"last_active": "now"},
      photo_file_path="photo.jpg",
      caption="What is this?",
  )

  system_lines = [line for line in memory.lines if line["role"] == "system"]
  assert system_lines
  assert "a lightsaber in hand" in system_lines[0]["line"]
  assert sender.calls == [(5, "reply:What is this?")]
