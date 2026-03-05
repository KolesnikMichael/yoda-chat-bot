import asyncio
import logging
import os
from pathlib import Path

from .affect import AffectOperation, AffectProvider
from .cognition import CognitionOperation
from .memory.memory import MemoryOperation, MemoryProvider
from .perception.audio import AudioOperation, AudioProvider
from .perception.language import LanguageProvider
from .perception.vision import VisionProvider

logger = logging.getLogger(__name__)


class Mind:
  def __init__(
      self,
      language_provider: LanguageProvider,
      vision_provider: VisionProvider,
      audio_provider: AudioProvider,
      memory_provider: MemoryProvider,
      affect_provider: AffectProvider,
  ):
    self.language_provider = language_provider
    self.vision_provider = vision_provider
    self.audio_provider = audio_provider
    self.memory_provider = memory_provider
    self.affect_provider = affect_provider
    self._message_sender = None

  def bind_message_sender(self, message_sender) -> None:
    self._message_sender = message_sender

  async def _process_text_pipeline(self, user_id: int, chat_id: int, text: str) -> str:
    normalized_text = CognitionOperation.normalize_user_text(text)
    emotional_state = self.affect_provider.get_emotional_state()
    system_prompt = AffectOperation.build_system_prompt(emotional_state)

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
    await self.memory_provider.update_sender_info(user_id, chat_id, user_info)
    chat_type = CognitionOperation.determine_chat_type(user_id, chat_id)
    await self.memory_provider.update_chat_info(
        chat_id=chat_id,
        chat_type=chat_type,
        last_active=user_info.get("last_active", ""),
    )
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=message_text)
    if self._message_sender:
      await self._message_sender(chat_id, reply)

  async def process_voice_message(self, user_id: int, chat_id: int, user_info: dict, audio_file_path):
    await self.memory_provider.update_sender_info(user_id, chat_id, user_info)
    chat_type = CognitionOperation.determine_chat_type(user_id, chat_id)
    await self.memory_provider.update_chat_info(
        chat_id=chat_id,
        chat_type=chat_type,
        last_active=user_info.get("last_active", ""),
    )
    wav_path = await asyncio.to_thread(AudioOperation.convert_ogg_to_wav, Path(audio_file_path))
    text = await self.audio_provider.speech_to_text(audio_file_path=wav_path)
    reply = await self._process_text_pipeline(user_id=user_id, chat_id=chat_id, text=text)
    if self._message_sender:
      await self._message_sender(chat_id, reply)
    if os.path.exists(audio_file_path):
      os.remove(audio_file_path)
    if os.path.exists(wav_path):
      os.remove(wav_path)

  async def process_photo_message(self, user_id: int, chat_id: int, user_info: dict, photo_file_path, caption: str):
    await self.memory_provider.update_sender_info(user_id, chat_id, user_info)
    chat_type = CognitionOperation.determine_chat_type(user_id, chat_id)
    await self.memory_provider.update_chat_info(
        chat_id=chat_id,
        chat_type=chat_type,
        last_active=user_info.get("last_active", ""),
    )

    image_description = await self.vision_provider.image_to_description(photo_file_path)
    emotional_state = self.affect_provider.get_emotional_state()
    system_prompt = AffectOperation.build_system_prompt(emotional_state)
    conversation = self.memory_provider.get_conversation(user_id=user_id, chat_id=chat_id)
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
    if os.path.exists(photo_file_path):
      os.remove(photo_file_path)
