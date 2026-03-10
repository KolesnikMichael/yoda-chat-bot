import datetime as dtm
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yoda.embodiment.telegram_bot import TelegramBot
from yoda.mind.memory.data.pending_message import PendingMessage


class FakeTelegramApi:
  def __init__(self):
    self.application = SimpleNamespace(bot=SimpleNamespace())
    self.registered = False
    self.ran = False

  def build_application(self, token: str):
    return self.application

  def register_handlers(self, **kwargs):
    self.registered = True

  def run_polling(self, application):
    self.ran = True

  async def download_voice_to_cache(self, message, cache_dir: str = "./.file_cache"):
    return "voice.ogg"

  async def download_photo_to_cache(self, message, cache_dir: str = "./.file_cache"):
    return "photo.jpg"

  async def send_typing_action(self, bot, chat_id: int):
    return None

  async def send_message(self, bot, chat_id: int, message: str):
    return None


def build_update(text: str = "hello", caption: str = "", media_group_id: str | None = None,
                 user_id: int = 42, chat_id: int = 100):
  from_user = SimpleNamespace(
      id=user_id,
      username="obiwan",
      first_name="Obi",
      last_name="Wan",
      language_code="en",
  )
  chat = SimpleNamespace(id=chat_id)
  message = SimpleNamespace(
      from_user=from_user,
      chat=chat,
      text=text,
      caption=caption,
      media_group_id=media_group_id,
      date=dtm.datetime.now(dtm.UTC),
      voice=SimpleNamespace(get_file=AsyncMock()),
      photo=[SimpleNamespace(get_file=AsyncMock())],
      reply_text=AsyncMock(),
  )
  return SimpleNamespace(message=message)


def build_context():
  scheduled = []
  removed = []

  def get_jobs(name):
    return [
        SimpleNamespace(schedule_removal=lambda n=j["name"]: removed.append(n))
        for j in scheduled if j["name"] == name
    ]

  job_queue = SimpleNamespace(
      get_jobs_by_name=get_jobs,
      run_once=lambda cb, when, data, name: scheduled.append(
          {"callback": cb, "data": data, "name": name, "when": when}
      ),
  )
  return SimpleNamespace(job_queue=job_queue), scheduled, removed


def build_bot(**overrides):
  defaults = dict(
      settings={"bot_token": "token", "bot_test_token": "test-token"},
      test_mode=True,
      telegram_api=FakeTelegramApi(),
  )
  return TelegramBot(**(defaults | overrides))


@pytest.mark.asyncio
async def test_text_handler_adds_to_pending_batch():
  bot = build_bot()
  context, scheduled, _ = build_context()

  await bot.handle_text_message(build_update(text="Hi"), context=context)

  assert 100 in bot._pending_batches
  batch = bot._pending_batches[100]
  assert len(batch) == 1
  assert batch[0].media_type == "text"
  assert batch[0].text == "Hi"
  assert batch[0].timestamp != ""
  assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_voice_handler_adds_to_pending_batch():
  bot = build_bot()
  context, scheduled, _ = build_context()

  await bot.handle_voice_message(build_update(), context=context)

  batch = bot._pending_batches[100]
  assert len(batch) == 1
  assert batch[0].media_type == "voice"
  assert batch[0].audio_file_path == "voice.ogg"


@pytest.mark.asyncio
async def test_photo_handler_adds_to_pending_batch():
  bot = build_bot()
  context, scheduled, _ = build_context()

  await bot.handle_photo_message(build_update(caption="look"), context=context)

  batch = bot._pending_batches[100]
  assert len(batch) == 1
  assert batch[0].media_type == "photo"
  assert batch[0].photo_file_paths == ["photo.jpg"]
  assert batch[0].caption == "look"


@pytest.mark.asyncio
async def test_grouped_photos_merge_into_single_pending_message():
  bot = build_bot()
  context, scheduled, removed = build_context()

  await bot.handle_photo_message(
      build_update(caption="look at these", media_group_id="g1"), context=context)
  await bot.handle_photo_message(
      build_update(media_group_id="g1"), context=context)

  batch = bot._pending_batches[100]
  assert len(batch) == 1
  assert len(batch[0].photo_file_paths) == 2
  assert batch[0].caption == "look at these"
  assert len(removed) == 1


@pytest.mark.asyncio
async def test_mixed_messages_accumulate_in_batch():
  bot = build_bot()
  context, _, _ = build_context()

  await bot.handle_text_message(build_update(text="Hi"), context=context)
  await bot.handle_photo_message(build_update(caption="photo"), context=context)
  await bot.handle_voice_message(build_update(), context=context)

  batch = bot._pending_batches[100]
  assert len(batch) == 3
  assert batch[0].media_type == "text"
  assert batch[1].media_type == "photo"
  assert batch[2].media_type == "voice"


@pytest.mark.asyncio
async def test_flush_batch_sends_to_mind():
  bot = build_bot()
  mind = SimpleNamespace(process_message_batch=AsyncMock())
  bot.mind = mind

  chat_id = 100
  bot._pending_batches[chat_id] = [
      PendingMessage(user_id=42, user_info={"last_active": "now"}, media_type="text", text="Hi"),
  ]

  flush_context = SimpleNamespace(job=SimpleNamespace(data=chat_id))
  await bot._flush_batch(flush_context)

  mind.process_message_batch.assert_awaited_once()
  kwargs = mind.process_message_batch.call_args.kwargs
  assert kwargs["chat_id"] == 100
  assert len(kwargs["batch"]) == 1
  assert chat_id not in bot._pending_batches


@pytest.mark.asyncio
async def test_batch_timeout_from_settings():
  bot = build_bot(settings={
      "bot_token": "token",
      "bot_test_token": "test-token",
      "message_batch_timeout": 3.0,
  })
  assert bot.batch_timeout == 3.0


@pytest.mark.asyncio
async def test_batch_timeout_default():
  bot = build_bot()
  assert bot.batch_timeout == 5.0


@pytest.mark.asyncio
async def test_timer_resets_on_each_message():
  bot = build_bot()
  context, scheduled, removed = build_context()

  await bot.handle_text_message(build_update(text="one"), context=context)
  await bot.handle_text_message(build_update(text="two"), context=context)

  assert len(bot._pending_batches[100]) == 2
  assert len(removed) == 1
  assert len(scheduled) == 2
