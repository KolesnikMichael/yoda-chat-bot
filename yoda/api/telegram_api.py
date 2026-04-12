import time

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

FILE_CACHE_DIR = "./.file_cache"

class TelegramApi:
    def build_application(self, token: str) -> Application:
        return Application.builder().token(token).build()

    def run_polling(self, application: Application) -> None:
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def send_typing_action(self, bot, chat_id: int) -> None:
        await bot.send_chat_action(chat_id=chat_id, action="TYPING")

    async def send_message(
        self,
        bot,
        chat_id: int,
        message: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        kwargs: dict = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        if reply_to_message_id is not None:
            kwargs["reply_to_message_id"] = reply_to_message_id
        await bot.send_message(**kwargs)

    async def download_voice_to_cache(self, message, cache_dir: str = FILE_CACHE_DIR) -> str:
        voice_file = await message.voice.get_file()
        return await voice_file.download_to_drive(custom_path=f"{cache_dir}/voice_{time.time()}.ogg")

    async def download_photo_to_cache(self, message, cache_dir: str = FILE_CACHE_DIR) -> str:
        photo_file = await message.photo[-1].get_file()
        return await photo_file.download_to_drive(custom_path=f"{cache_dir}/photo_{time.time()}.jpg")

    def register_handlers(
        self,
        application: Application,
        start_handler,
        reset_handler,
        settings_handler,
        help_handler,
        text_handler,
        voice_handler,
        photo_handler,
    ) -> None:
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("reset", reset_handler))
        application.add_handler(CommandHandler("settings", settings_handler))
        application.add_handler(CommandHandler("help", help_handler))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, text_handler))
        application.add_handler(MessageHandler(filters.VOICE, voice_handler))
        application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
