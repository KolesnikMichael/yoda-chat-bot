import datetime as dtm
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yoda.embodiment.telegram_bot import TelegramBot


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


def build_update(text: str = "hello", caption: str = "", media_group_id: str | None = None):
  from_user = SimpleNamespace(
      id=42,
      username="obiwan",
      first_name="Obi",
      last_name="Wan",
      language_code="en",
  )
  chat = SimpleNamespace(id=100)
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


@pytest.mark.asyncio
async def test_text_handler_routes_to_mind():
  telegram_api = FakeTelegramApi()
  bot = TelegramBot(
      settings={"bot_token": "token", "bot_test_token": "test-token"},
      test_mode=True,
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_text_message=AsyncMock())
  bot.mind = mind

  await bot.handle_text_message(build_update(text="Hi"), context=None)

  mind.process_text_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_handler_routes_to_mind():
  telegram_api = FakeTelegramApi()
  bot = TelegramBot(
      settings={"bot_token": "token", "bot_test_token": "test-token"},
      test_mode=False,
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_voice_message=AsyncMock())
  bot.mind = mind

  await bot.handle_voice_message(build_update(text="ignored"), context=None)

  mind.process_voice_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_photo_routes_to_mind():
  telegram_api = FakeTelegramApi()
  bot = TelegramBot(
      settings={"bot_token": "token", "bot_test_token": "test-token"},
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_photo_message=AsyncMock())
  bot.mind = mind

  await bot.handle_photo_message(build_update(caption="look"), context=None)

  mind.process_photo_message.assert_awaited_once()
  kwargs = mind.process_photo_message.call_args.kwargs
  assert kwargs["photo_file_paths"] == ["photo.jpg"]
  assert kwargs["caption"] == "look"


@pytest.mark.asyncio
async def test_grouped_photos_accumulate_before_routing_to_mind():
  telegram_api = FakeTelegramApi()
  bot = TelegramBot(
      settings={"bot_token": "token", "bot_test_token": "test-token"},
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_photo_message=AsyncMock())
  bot.mind = mind

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
          {"callback": cb, "data": data, "name": name}
      ),
  )
  context = SimpleNamespace(job_queue=job_queue)

  await bot.handle_photo_message(
      build_update(caption="look at these", media_group_id="g1"), context=context,
  )
  await bot.handle_photo_message(
      build_update(media_group_id="g1"), context=context,
  )

  mind.process_photo_message.assert_not_awaited()
  group = bot._pending_groups[(100, "g1")]
  assert len(group["photo_file_paths"]) == 2
  assert group["caption"] == "look at these"
  assert len(removed) == 1


@pytest.mark.asyncio
async def test_flush_media_group_sends_accumulated_to_mind():
  telegram_api = FakeTelegramApi()
  bot = TelegramBot(
      settings={"bot_token": "token", "bot_test_token": "test-token"},
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_photo_message=AsyncMock())
  bot.mind = mind

  key = (100, "g1")
  bot._pending_groups[key] = {
      "user_id": 42, "chat_id": 100,
      "user_info": {"last_active": "now"},
      "caption": "look at these",
      "photo_file_paths": ["photo1.jpg", "photo2.jpg"],
  }

  flush_context = SimpleNamespace(job=SimpleNamespace(data=key))
  await bot._flush_media_group(flush_context)

  mind.process_photo_message.assert_awaited_once_with(
      user_id=42, chat_id=100,
      user_info={"last_active": "now"},
      photo_file_paths=["photo1.jpg", "photo2.jpg"],
      caption="look at these",
  )
  assert key not in bot._pending_groups
