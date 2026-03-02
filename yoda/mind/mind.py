import logging

from .affect import AffectOperation, AffectProvider
from .cognition import CognitionOperation
from .memory.memory import MemoryOperation, MemoryProvider
from .perception.audio import AudioProvider
from .perception.language import LanguageProvider
from .perception.vision import VisionProvider

logger = logging.getLogger(__name__)


class Mind:
  def __init__(
      self,
      settings: dict,
      memory_provider=None,
      affect_provider=None,
      language_provider=None,
      audio_provider=None,
      vision_provider=None,
  ):
    reason_settings = settings["reason"]

    self.memory_provider = memory_provider \
      or MemoryProvider.from_settings(settings["memory"])
    self.language_provider = language_provider \
      or LanguageProvider.from_settings(reason_settings["intelligence"]["language_processing"])
    self.audio_provider = audio_provider \
      or AudioProvider.from_settings(settings.get("audio", {}))
    self.vision_provider = vision_provider \
      or VisionProvider.from_settings(reason_settings["intelligence"]["computer_vision"])
    self.affect_provider = affect_provider \
      or AffectProvider.from_settings(settings["emotions"])

    self._message_sender = None

  def bind_message_sender(self, message_sender) -> None:
    self._message_sender = message_sender

  async def _process_text_pipeline(self, user_id: int, chat_id: int, text: str) -> str:
    normalized_text = CognitionOperation.normalize_user_text(text)
    emotion_state = self.affect_provider.get_emotion_state()
    system_prompt = AffectOperation.build_system_prompt(emotion_state)

    conversation = self.memory_provider.get_conversation(user_id=user_id, chat_id=chat_id)
    conversation, messages = MemoryOperation.add_conversation_line(
        conversation=conversation,
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        line=normalized_text,
        system_prompt=system_prompt,
    )
    self.memory_provider.save_conversation(conversation)

    reply = await self.language_provider.reply_in_conversation(messages)
    conversation, _ = MemoryOperation.add_conversation_line(
        conversation=conversation,
        user_id=user_id,
        chat_id=chat_id,
        role="assistant",
        line=reply,
        system_prompt=system_prompt,
    )
    self.memory_provider.save_conversation(conversation)
    return reply

  async def process_text_message(self, user_id: int, chat_id: int, user_info: dict, message_text: str):
    logger.info(f"Got text message from {user_id}@{chat_id}")
    await self.memory_provider.update_sender_info(user_id, chat_id, user_info)
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=message_text)
    if self._message_sender:
      await self._message_sender(chat_id, reply)

  async def process_voice_message(self, user_id: int, chat_id: int, user_info: dict, audio_file_path):
    logger.info(f"Got voice message from {user_id}@{chat_id}")
    await self.memory_provider.update_sender_info(user_id, chat_id, user_info)
    text = await self.audio_provider.speech_to_text(audio_file_path=audio_file_path, language="ru-RU")
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=text)
    if self._message_sender:
      await self._message_sender(chat_id, reply)

  async def process_photo_message(self, user_id: int, chat_id: int, user_info: dict, photo_file_path, caption: str):
    logger.info(f"Got photo message from {user_id}@{chat_id}")
    await self.memory_provider.update_sender_info(user_id, chat_id, user_info)

    image_description = await self.vision_provider.image_to_description(photo_file_path)
    emotion_state = self.affect_provider.get_emotion_state()
    system_prompt = AffectOperation.build_system_prompt(emotion_state)
    conversation = self.memory_provider.get_conversation(user_id=user_id, chat_id=chat_id)
    conversation, _ = MemoryOperation.add_conversation_line(
        conversation=conversation,
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        line="",
        system_prompt=system_prompt,
    ) # Mistral won't accept system message with no preceeding user message
    conversation, _ = MemoryOperation.add_conversation_line(
        conversation=conversation,
        user_id=user_id,
        chat_id=chat_id,
        role="system",
        line=f"User sent an image with description: {image_description}",
        system_prompt=system_prompt,
    )
    self.memory_provider.save_conversation(conversation)
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=caption)
    if self._message_sender:
      await self._message_sender(chat_id, reply)
