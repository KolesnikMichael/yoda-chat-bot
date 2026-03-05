import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

from yoda.api.telegram_api import TelegramApi

logger = logging.getLogger(__name__)


class TelegramBot:
  def __init__(self, settings, test_mode: bool = False, telegram_api: TelegramApi | None = None):
    self.settings = settings
    self.telegram_api = telegram_api or TelegramApi()

    token_key = "bot_test_token" if test_mode else "bot_token"
    try:
      bot_token = settings[token_key]
    except KeyError as e:
      raise ValueError(f"Telegram settings missing required '{token_key}'") from e

    self.application = self.telegram_api.build_application(bot_token)
    self.bot = self.application.bot

    self.register_handlers()

  def wake_up(self, mind):
    self.mind = mind
    self.mind.bind_message_sender(self.send_message)
    self.telegram_api.run_polling(self.application)

  async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, chat_id, user_info = self.get_user_details(update.message)
    logger.info(f"Got text message from {user_id}@{chat_id}")

    message_text = update.message.text
    await self.mind.process_text_message(user_id=user_id, chat_id=chat_id, user_info=user_info, message_text=message_text)

  async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, chat_id, user_info = self.get_user_details(update.message)
    logger.info(f"Got voice message from {user_id}@{chat_id}")

    audio_file_path = await self.telegram_api.download_voice_to_cache(update.message)
    await self.mind.process_voice_message(user_id=user_id, chat_id=chat_id, user_info=user_info, audio_file_path=audio_file_path)

  async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, chat_id, user_info = self.get_user_details(update.message)
    logger.info(f"Got photo message from {user_id}@{chat_id}")

    photo_file_path = await self.telegram_api.download_photo_to_cache(update.message)
    caption = update.message.caption or ""
    await self.mind.process_photo_message(user_id=user_id, chat_id=chat_id, user_info=user_info, photo_file_path=photo_file_path, caption=caption)

  async def send_message(self, chat_id: int, message: str) -> None:
    for _ in range(3):
      await asyncio.sleep(1)
      await self.telegram_api.send_typing_action(self.bot, chat_id=chat_id)
    await self.telegram_api.send_message(self.bot, chat_id=chat_id, message=message)

  async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text("Start!")

  async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /reset is issued."""
    await update.message.reply_text("Reset!")

  async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /settings is issued."""
    await update.message.reply_text("Settings!")

  async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")

  def get_user_details(self, message):
    user_info = {
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "language_code": message.from_user.language_code,
        "last_active": f"{message.date}"
    }
    return message.from_user.id, message.chat.id, user_info

  def register_handlers(self):
    self.telegram_api.register_handlers(
        application=self.application,
        start_handler=self.start_command,
        reset_handler=self.reset_command,
        settings_handler=self.settings_command,
        help_handler=self.help_command,
        text_handler=self.handle_text_message,
        voice_handler=self.handle_voice_message,
        photo_handler=self.handle_photo_message,
    )
