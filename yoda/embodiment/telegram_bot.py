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
            bot_token =  settings["bot_token"]
            
        self.application = Application.builder().token(bot_token).build()
        self.bot = self.application.bot

        self.register_handlers()

    def register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("reset", self.reset_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo_message))


    def wake_up(self, mind):
        self.mind = mind
        self.mind.wake_up(self)
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    def get_user_data(self, message):
        return {
            "id": f"{message.chat_id}:{message.from_user.id}",
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "language_code": message.from_user.language_code
            }

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

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_data = self.get_user_data(update.message)
        logger.info(f"Got text message from {user_data['id']}")
        message_timestamp = update.message.date.timestamp()

        message_text = update.message.text
        await self.mind.process_text_message(user_data, message_text, message_timestamp)


    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_data = self.get_user_data(update.message)
        logger.info(f"Got voice message from {user_data['id']}")
        message_timestamp = update.message.date.timestamp()

        voice_file = await update.message.voice.get_file()
        audio_file_path = await voice_file.download_to_drive(custom_path=f"./.file_cache/voice_{time.time()}.ogg")
        await self.mind.process_voice_message(user_data, audio_file_path, message_timestamp)


    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_data = self.get_user_data(update.message)
        logger.info(f"Got photo message from {user_data['id']}")
        message_timestamp = update.message.date.timestamp()

        caption = update.message.caption or ""
        photo_file = await update.message.photo[-1].get_file()
        photo_file_path = await photo_file.download_to_drive(custom_path=f"./.file_cache/photo_{time.time()}.jpg")
        await self.mind.process_photo_message(user_data, photo_file_path, caption, message_timestamp)


    async def send_message(self, user_id, message) -> None:
        chat_id = user_id.split(":")[0]
        for _ in range(3):
            time.sleep(1)
            await self.bot.send_chat_action(chat_id=chat_id, action="TYPING")
        await self.bot.send_message(chat_id=chat_id, text=message) 


