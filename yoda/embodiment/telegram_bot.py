import logging
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)


class TelegramBot:
  def __init__(self, settings, test_mode=False):
    self.settings = settings

    if test_mode:
      bot_token = settings["bot_token_test"]
    else:
      bot_token = settings["bot_token"]

    self.application = Application.builder().token(bot_token).build()
    self.bot = self.application.bot

    self.register_handlers()

  def wake_up(self, mind):
    self.mind = mind
    self.mind.wake_up(self)
    self.application.run_polling(allowed_updates=Update.ALL_TYPES)

  async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    user_info = self.get_user_info(update.message)
    logger.info(f"Got text message from {user_id}@{chat_id}")

    message_text = update.message.text
    await self.mind.process_text_message(user_id=user_id, chat_id=chat_id, user_info=user_info, message_text=message_text)

  async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    user_info = self.get_user_info(update.message)
    logger.info(f"Got voice message from {user_id}@{chat_id}")

    voice_file = await update.message.voice.get_file()
    audio_file_path = await voice_file.download_to_drive(custom_path=f"./.file_cache/voice_{time.time()}.ogg")
    await self.mind.process_voice_message(user_id=user_id, chat_id=chat_id, user_info=user_info, audio_file_path=audio_file_path)

  async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    user_info = self.get_user_info(update.message)
    logger.info(f"Got photo message from {user_id}@{chat_id}")

    photo_file = await update.message.photo[-1].get_file()
    photo_file_path = await photo_file.download_to_drive(custom_path=f"./.file_cache/photo_{time.time()}.jpg")
    caption = update.message.caption or ""
    await self.mind.process_photo_message(user_id=user_id, chat_id=chat_id, user_info=user_info, photo_file_path=photo_file_path, caption=caption)

  async def send_message(self, chat_id: int, message: str) -> None:
    for _ in range(3):
      time.sleep(1)
      await self.bot.send_chat_action(chat_id=chat_id, action="TYPING")
    await self.bot.send_message(chat_id=chat_id, text=message)

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

  def get_user_info(self, message):
    user_info = {
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "language_code": message.from_user.language_code,
        "last_active": f"{message.date}"
    }
    return user_info

  def register_handlers(self):
    self.application.add_handler(CommandHandler("start", self.start_command))
    self.application.add_handler(CommandHandler("reset", self.reset_command))
    self.application.add_handler(
        CommandHandler("settings", self.settings_command))
    self.application.add_handler(CommandHandler("help", self.help_command))
    self.application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, self.handle_text_message))
    self.application.add_handler(MessageHandler(
        filters.VOICE, self.handle_voice_message))
    self.application.add_handler(MessageHandler(
        filters.PHOTO, self.handle_photo_message))
