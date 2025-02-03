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


    def process_text_message(self, user, message_text):
        text = message_text
        response = self.reason.process_text(user, text)
        return response
    

    async def send_text_message(self, user, message_text):
        await self.bot.send_message(user, message_text)



