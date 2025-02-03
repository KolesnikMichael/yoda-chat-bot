import logging
from mind.reason.intelligence.language_processing import LanguageProcessing

logger = logging.getLogger(__name__)

class Reason:
    def __init__(self, mind, settings):
        self.mind = mind
        self.language_processing = LanguageProcessing(settings["intelligence"]["language_processing"])
        self.conversations = {}

    async def process_text(self, user, text):
        if user not in self.conversations:
            logger.info("Starting new conversation")
            self.conversations[user] = [{"role": "user", "content": "Reply as Yoda from Star Wars"}]

        self.conversations[user].append({"role": "user", "content": text})

        reply = await self.language_processing.keep_conversation(self.conversations[user])

        self.conversations[user].append({"role": "user", "content": reply})

        await self.mind.send_text_message(user, reply)   
