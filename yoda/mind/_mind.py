import logging
from ._reason import Reason
from ._emotions import Emotions
from ._memory import Memory

logger = logging.getLogger(__name__)

class Mind:
    def __init__(self, settings):
        self.reason = Reason(self, settings["reason"])
        self.memory = Memory(self, settings["memory"])
        self.emotions = Emotions(self, settings["emotions"])


    def wake_up(self, bot):
        self.bot = bot


    def process_text_message(self, user_id: int, chat_id: int, user_info: dict, message_text: str):
        logger.info(f"Got text message from {user_id}@{chat_id}")
        self.memory.update_sender_info(user_id, chat_id, user_info)
        response = self.reason.process_text(user_id=user_id, chat_id=chat_id, text=message_text)
        return response


    def process_voice_message(self, user_id: int, chat_id: int, user_info: dict, audio_file_path):
        logger.info(f"Got voice message from {user_id}@{chat_id}")
        self.memory.update_sender_info(user_id, chat_id, user_info)
        response = self.reason.process_voice(user_id=user_id, chat_id=chat_id, audio_file_path=audio_file_path)
        return response


    def process_photo_message(self, user_id: int, chat_id: int, user_info: dict, photo_file_path, caption: str):
        logger.info(f"Got photo message from {user_id}@{chat_id}")
        self.memory.update_sender_info(user_id, chat_id, user_info)
        response = self.reason.process_image(user_id, chat_id, photo_file_path, caption)
        return response


    async def send_text_message(self, chat_id: int, text_message: str):
        await self.bot.send_message(chat_id, text_message)
