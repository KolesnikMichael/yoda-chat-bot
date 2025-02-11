import logging
from mistralai import Mistral

logger = logging.getLogger(__name__)

class LanguageProcessor:
    def __init__(self, settings):
        self.mistral_client = Mistral(api_key=settings["mistral_large_latest"]["api_key"])
        self.model_name = settings["mistral_large_latest"]["model_name"]

    async def reply_in_conversation(self, conversation):
        response  = await self.mistral_client.chat.complete_async(
            model = self.model_name,
            messages = conversation)
        return response.choices[0].message.content
        # return "Hmmm, ignore your message, you want me to? Very well, young one, ignored it will be."