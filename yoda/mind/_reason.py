import logging
from .intelligence.language import LanguageProcessor
from .intelligence.speech import SpeechRecognizer
from .intelligence.vision import ComputerVision
from .conversation import Conversation

logger = logging.getLogger(__name__)

class Reason:
    def __init__(self, mind, settings):
        self.mind = mind
        self.language_processor = LanguageProcessor(settings["intelligence"]["language_processing"])
        self.speech_recognition = SpeechRecognizer()
        self.computer_vision = ComputerVision(settings["intelligence"]["computer_vision"])
        self.conversation = Conversation()

    async def convert_audio_to_text(self, audio_file_path, language):
        text = self.speech_recognition.speech_to_text(audio_file_path, language)
        return text
    

    async def process_text(self, user, text, message_time):
        logger.info(f"Got text message from {user}")

        messages = self.conversation.add(user=user, role="user", line=text)

        reply = await self.language_processor.reply_in_conversation(messages)
        self.conversation.add(user=user, role="assistant", line=reply)

        await self.mind.send_text_message(user, reply)   


    async def process_voice(self, user, audio_file_path, message_time, language="ru-RU"):
        logger.info(f"Got voice message from {user}")

        text = await self.convert_audio_to_text(audio_file_path, language)   

        await self.process_text(user, text, message_time)


    async def process_image(self, user, photo_file_path, caption, message_time):
        logger.info(f"Got image message from {user}")

        image_description = self.computer_vision.image_to_description(photo_file_path)

        self.conversation.add(user=user, role="user") # Mistral accepts "system" message only after "user" message
        self.conversation.add(user=user, role="system", line=f"User sent an image with description: {image_description}")

        await self.process_text(user, caption, message_time)  
