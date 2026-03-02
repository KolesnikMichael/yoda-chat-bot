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

  async def emulate_typing(self, bot, chat_id: int, seconds: int):
    return None

  async def send_message(self, bot, chat_id: int, message: str):
    return None


def build_update(text: str = "hello", caption: str = ""):
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
      settings={"bot_token": "token", "bot_token_test": "test-token"},
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
      settings={"bot_token": "token", "bot_token_test": "test-token"},
      test_mode=False,
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_voice_message=AsyncMock())
  bot.mind = mind

  await bot.handle_voice_message(build_update(text="ignored"), context=None)

  mind.process_voice_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_handler_routes_to_mind():
  telegram_api = FakeTelegramApi()
  bot = TelegramBot(
      settings={"bot_token": "token", "bot_token_test": "test-token"},
      telegram_api=telegram_api,
  )
  mind = SimpleNamespace(process_photo_message=AsyncMock())
  bot.mind = mind

  await bot.handle_photo_message(build_update(caption="look"), context=None)

  mind.process_photo_message.assert_awaited_once()
