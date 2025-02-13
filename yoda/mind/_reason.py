import logging
from .intelligence.language import LanguageProcessor
from .intelligence.speech import SpeechRecognizer
from .intelligence.vision import ComputerVision
from .conversation import Conversation

logger = logging.getLogger(__name__)

class Reason:
    def __init__(self, mind, settings: dict):
        self.mind = mind
        self.language_processor = LanguageProcessor(settings["intelligence"]["language_processing"])
        self.speech_recognition = SpeechRecognizer()
        self.computer_vision = ComputerVision(settings["intelligence"]["computer_vision"])
        self.conversation = Conversation()


    async def convert_audio_to_text(self, audio_file_path, language: str):
        text = self.speech_recognition.speech_to_text(audio_file_path=audio_file_path, language=language)
        return text
    

    async def process_text(self, user_id: int, chat_id: int, text: str):
        logger.info(f"Got text message from {user_id}@{chat_id}")

        messages = self.conversation.add_line(user_id=user_id, chat_id=chat_id, role="user", line=text)

        reply = await self.language_processor.reply_in_conversation(messages)
        self.conversation.add_line(user_id=user_id, chat_id=chat_id, role="assistant", line=reply)

        await self.mind.send_text_message(chat_id=chat_id, text_message=reply)   


    async def process_voice(self, user_id: int, chat_id: int, audio_file_path, language="ru-RU"):
        logger.info(f"Got voice message from {user_id}@{chat_id}")

        text = await self.convert_audio_to_text(audio_file_path=audio_file_path, language=language)   

        await self.process_text(user_id=user_id, chat_id=chat_id, text=text)


    async def process_image(self, user_id: int, chat_id: int, photo_file_path, caption: str):
        logger.info(f"Got image message from {user_id}@{chat_id}")

        image_description = self.computer_vision.image_to_description(photo_file_path)

        self.conversation.add_line(user_id=user_id, chat_id=chat_id, role="user") # Adding an empty "user" line before "system" message due to Mistral restricstion
        self.conversation.add_line(user_id=user_id, chat_id=chat_id, role="system", line=f"User sent an image with description: {image_description}")

        await self.process_text(user_id=user_id, chat_id=chat_id, text=caption)  
