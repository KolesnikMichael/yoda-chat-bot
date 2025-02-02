from mind.reason._reason import Reason
from mind.emotions import Emotions
from mind.memory import Memory

class Mind:
    def __init__(self, settings, logger):
        self.logger = logger
        self.reason = Reason(self, settings["reason"], logger)
        self.memory = Memory(self, settings["memory"], logger)
        self.emotions = Emotions(self, settings["emotions"], logger)

    def wake_up(self, bot):
        self.bot = bot


    def process_text_message(self, user, message_text):
        text = message_text
        response = self.reason.process_text(user, text)
        return response
    

    async def send_text_message(self, user, message_text):
        await self.bot.send_message(user, message_text)



