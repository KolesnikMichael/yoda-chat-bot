import logging
from mind.reason.intelligence.language_processing import LanguageProcessor
from mind.reason.intelligence.speech_recognition import SpeechRecognizer
from mind.reason.intelligence.computer_vision import ComputerVision

logger = logging.getLogger(__name__)

class Reason:
    def __init__(self, mind, settings):
        self.mind = mind
        self.language_processor = LanguageProcessor(settings["intelligence"]["language_processing"])
        self.speech_recognition = SpeechRecognizer()
        self.computer_vision = ComputerVision(settings["intelligence"]["computer_vision"])
        self.conversations = {}

    async def convert_audio_to_text(self, audio_file_path, language):
        text = self.speech_recognition.speech_to_text(audio_file_path, language)
        return text
    

    async def process_text(self, user, text):
        logger.info(f"Got text message from {user}")

        if user not in self.conversations:
            logger.info(f"Starting new conversation with {user}")
            self.conversations[user] = [{"role": "user", "content": "Reply as Yoda from Star Wars"}]

        self.conversations[user].append({"role": "user", "content": text})

        reply = await self.language_processor.reply_in_conversation(self.conversations[user])

        self.conversations[user].append({"role": "user", "content": reply})

        await self.mind.send_text_message(user, reply)   


    async def process_voice(self, user, audio_file_path, language="ru-RU"):
        logger.info(f"Got voice message from {user}")

        if user not in self.conversations:
            logger.info("Starting new conversation")
            self.conversations[user] = [{"role": "user", "content": "Reply as Yoda from Star Wars"}]

        text = await self.convert_audio_to_text(audio_file_path, language)   

        self.conversations[user].append({"role": "user", "content": text})

        reply = await self.language_processor.reply_in_conversation(self.conversations[user])

        self.conversations[user].append({"role": "user", "content": reply})

        await self.mind.send_text_message(user, reply)   


    async def process_image(self, user, photo_file_path, caption):
        logger.info(f"Got image message from {user}")

        if user not in self.conversations:
            logger.info("Starting new conversation")
            self.conversations[user] = [{"role": "user", "content": "Reply as Yoda from Star Wars"}]

        image_description = self.computer_vision.image_to_description(photo_file_path)

        self.conversations[user].append({"role": "system", "content": f"User sent an image with description: {image_description}"})
        self.conversations[user].append({"role": "user", "content": caption})

        reply = await self.language_processor.reply_in_conversation(self.conversations[user])

        self.conversations[user].append({"role": "user", "content": reply})

        await self.mind.send_text_message(user, reply)   
