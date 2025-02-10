import logging
from mind.reason._reason import Reason
from mind.emotions import Emotions
from mind.memory import Memory

logger = logging.getLogger(__name__)

class Mind:
    def __init__(self, settings):
        self.reason = Reason(self, settings["reason"])
        self.memory = Memory(self, settings["memory"])
        self.emotions = Emotions(self, settings["emotions"])

    def wake_up(self, bot):
        self.bot = bot


    def process_text_message(self, user, message_text, message_time):
        user = user['id']
        logger.info(f"Got text message from {user}")
        response = self.reason.process_text(user, message_text, message_time)
        return response
    

    def process_voice_message(self, user, audio_file_path, message_time):
        user = user['id']
        logger.info(f"Got voice message from {user}")
        response = self.reason.process_voice(user, audio_file_path, message_time)
        return response
    

    def process_photo_message(self, user, photo_file_path, caption, message_time):
        user = user['id']
        logger.info(f"Got photo message from {user}")
        response = self.reason.process_image(user, photo_file_path, caption, message_time)
        return response

    
    async def send_text_message(self, user, message_text):
        await self.bot.send_message(user, message_text)



