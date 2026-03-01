import logging

from yoda.api.llm_api import LLMApi
from yoda.api.speech_api import SpeechApi
from yoda.api.storage_api import StorageApi

from .affect import AffectOperation
from .cognition import CognitionOperation
from .memory.memory import MemoryOperation
from .perception.audio import AudioProviderOperation
from .perception.language import LanguageProviderOperation
from .perception.vision import VisionProviderOperation

logger = logging.getLogger(__name__)


class Mind:
  def __init__(
      self,
      settings: dict,
      memory_operation=None,
      cognition_operation=None,
      affect_operation=None,
      language_provider=None,
      audio_provider=None,
      vision_provider=None,
  ):
    reason_settings = settings["reason"]
    memory_settings = settings["memory"]
    emotions_settings = settings["emotions"]
    if memory_operation:
      self.memory = memory_operation
    else:
      storage_api = StorageApi(
          host=memory_settings.get("redis_host", "localhost"),
          port=memory_settings.get("redis_port", 6379),
          db=memory_settings.get("redis_db", 0),
      )
      self.memory = MemoryOperation(storage_api=storage_api)

    self.cognition = cognition_operation or CognitionOperation()
    self.affect = affect_operation or AffectOperation()
    if language_provider:
      self.language_provider = language_provider
    else:
      language_llm_api = LLMApi(
          api_key=reason_settings["intelligence"]["language_processing"]["mistral_large_latest"]["api_key"]
      )
      self.language_provider = LanguageProviderOperation(
          settings=reason_settings["intelligence"]["language_processing"],
          llm_api=language_llm_api,
      )

    self.audio_provider = audio_provider or AudioProviderOperation(speech_api=SpeechApi())
    if vision_provider:
      self.vision_provider = vision_provider
    else:
      vision_llm_api = LLMApi(
          api_key=reason_settings["intelligence"]["computer_vision"]["pixtral_large_latest"]["api_key"]
      )
      self.vision_provider = VisionProviderOperation(
          settings=reason_settings["intelligence"]["computer_vision"],
          llm_api=vision_llm_api,
      )
    self.emotions = emotions_settings
    self._message_sender = None

  def bind_message_sender(self, message_sender) -> None:
    self._message_sender = message_sender

  async def _process_text_pipeline(self, user_id: int, chat_id: int, text: str) -> str:
    normalized_text = self.cognition.normalize_user_text(text)
    system_prompt = self.affect.build_system_prompt()

    messages = self.memory.add_conversation_line(
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        line=normalized_text,
        system_prompt=system_prompt,
    )

    reply = await self.language_provider.reply_in_conversation(messages)
    self.memory.add_conversation_line(
        user_id=user_id,
        chat_id=chat_id,
        role="assistant",
        line=reply,
        system_prompt=system_prompt,
    )
    return reply

  async def process_text_message(self, user_id: int, chat_id: int, user_info: dict, message_text: str):
    logger.info("Got text message from %s@%s", user_id, chat_id)
    await self.memory.update_sender_info(user_id, chat_id, user_info)
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=message_text)
    if self._message_sender:
      await self._message_sender(chat_id, reply)

  async def process_voice_message(self, user_id: int, chat_id: int, user_info: dict, audio_file_path):
    logger.info("Got voice message from %s@%s", user_id, chat_id)
    await self.memory.update_sender_info(user_id, chat_id, user_info)
    text = await self.audio_provider.speech_to_text(audio_file_path=audio_file_path, language="ru-RU")
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=text)
    if self._message_sender:
      await self._message_sender(chat_id, reply)

  async def process_photo_message(self, user_id: int, chat_id: int, user_info: dict, photo_file_path, caption: str):
    logger.info("Got photo message from %s@%s", user_id, chat_id)
    await self.memory.update_sender_info(user_id, chat_id, user_info)

    image_description = await self.vision_provider.image_to_description(photo_file_path)
    system_prompt = self.affect.build_system_prompt()
    self.memory.add_conversation_line(
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        line="",
        system_prompt=system_prompt,
    ) # Mistral won't accept system message with no preceeding user message
    self.memory.add_conversation_line(
        user_id=user_id,
        chat_id=chat_id,
        role="system",
        line=f"User sent an image with description: {image_description}",
        system_prompt=system_prompt,
    )
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=caption)
    if self._message_sender:
      await self._message_sender(chat_id, reply)
