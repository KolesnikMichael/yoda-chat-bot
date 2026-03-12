import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

from yoda.api.telegram_api import TelegramApi
from yoda.mind.memory.data.pending_message import PendingMessage

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, settings, test_mode: bool = False, telegram_api: TelegramApi | None = None):
        self.settings = settings
        self.telegram_api = telegram_api or TelegramApi()
        self._pending_batches: dict[int, list[PendingMessage]] = {}
        self.batch_timeout = settings.get("message_batch_timeout", 5.0)

        token_key = "bot_test_token" if test_mode else "bot_token"
        try:
            bot_token = settings[token_key]
        except KeyError as e:
            raise ValueError(
                f"Telegram settings missing required '{token_key}'") from e

        self.application = self.telegram_api.build_application(bot_token)
        self.bot = self.application.bot

        self.register_handlers()

    def _find_pending_photo_group(self, chat_id: int, media_group_id: str) -> PendingMessage | None:
        for pm in self._pending_batches.get(chat_id, []):
            if pm.media_group_id == media_group_id:
                return pm
        return None

    def _add_to_batch(self, chat_id: int, pending: PendingMessage, context: ContextTypes.DEFAULT_TYPE) -> None:
        if chat_id not in self._pending_batches:
            self._pending_batches[chat_id] = []
        self._pending_batches[chat_id].append(pending)
        self._reset_batch_timer(chat_id, context)

    def _reset_batch_timer(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        job_name = f"batch_{chat_id}"
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        context.job_queue.run_once(
            self._flush_batch, when=self.batch_timeout,
            data=chat_id, name=job_name,
        )

    async def _flush_batch(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = context.job.data
        batch = self._pending_batches.pop(chat_id, None)
        if not batch:
            return
        await self.mind.process_message_batch(chat_id=chat_id, batch=batch)

    def wake_up(self, mind):
        self.mind = mind
        self.mind.bind_message_sender(self.send_message)
        self.telegram_api.run_polling(self.application)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id, chat_id, user_info, timestamp = self.get_message_info(
            update.message)
        logger.info(f"Got text message from {user_id}@{chat_id}")

        pending = PendingMessage(
            user_id=user_id,
            user_info=user_info,
            media_type="text",
            text=update.message.text,
            timestamp=timestamp,
        )
        self._add_to_batch(chat_id, pending, context)

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id, chat_id, user_info, timestamp = self.get_message_info(
            update.message)
        logger.info(f"Got voice message from {user_id}@{chat_id}")

        audio_file_path = await self.telegram_api.download_voice_to_cache(update.message)
        pending = PendingMessage(
            user_id=user_id,
            user_info=user_info,
            media_type="voice",
            audio_file_path=audio_file_path,
            timestamp=timestamp,
        )
        self._add_to_batch(chat_id, pending, context)

    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id, chat_id, user_info, timestamp = self.get_message_info(
            update.message)
        logger.info(f"Got photo message from {user_id}@{chat_id}")

        photo_file_path = await self.telegram_api.download_photo_to_cache(update.message)
        caption = update.message.caption or ""
        media_group_id = update.message.media_group_id

        if media_group_id:
            existing = self._find_pending_photo_group(chat_id, media_group_id)
            if existing:
                existing.photo_file_paths.append(photo_file_path)
                if caption:
                    existing.caption = caption
                self._reset_batch_timer(chat_id, context)
                return

        pending = PendingMessage(
            user_id=user_id,
            user_info=user_info,
            media_type="photo",
            photo_file_paths=[photo_file_path],
            caption=caption,
            media_group_id=media_group_id,
            timestamp=timestamp,
        )
        self._add_to_batch(chat_id, pending, context)

    def get_message_info(self, message) -> tuple[int, int, dict, str]:
        timestamp = f"{message.date}"
        user_info = {
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "language_code": message.from_user.language_code,
            "last_active": timestamp,
        }
        return message.from_user.id, message.chat.id, user_info, timestamp

    async def send_message(self, chat_id: int, message: str) -> None:
        for _ in range(3):
            await asyncio.sleep(1)
            await self.telegram_api.send_typing_action(self.bot, chat_id=chat_id)
        await self.telegram_api.send_message(self.bot, chat_id=chat_id, message=message)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Start!")

    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Reset!")

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Settings!")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Help!")

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
