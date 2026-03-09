import asyncio
import logging
import os
from pathlib import Path

from yoda.mind.memory.data.pending_message import PendingMessage

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

  async def process_message_batch(self, chat_id: int, batch: list[PendingMessage]) -> None:
    if not batch:
      return

    chat_type = CognitionOperation.determine_chat_type(batch[0].user_id, chat_id)

    unique_users = {msg.user_id: msg.user_info for msg in batch}
    last_active = batch[-1].user_info.get("last_active", "")
    await asyncio.gather(
        *(self.memory_provider.update_sender_info(uid, chat_id, uinfo)
          for uid, uinfo in unique_users.items()),
        self.memory_provider.update_chat_info(
            chat_id=chat_id, chat_type=chat_type, last_active=last_active),
    )

    perceived = await asyncio.gather(
        *(self._perceive_message(msg, chat_type) for msg in batch)
    )

    emotional_state = self.affect_provider.get_emotional_state()
    system_prompt = AffectOperation.build_system_prompt(emotional_state)
    conversation = self.memory_provider.get_conversation(chat_id=chat_id)

    messages = None
    for entry in perceived:
      conversation, messages = MemoryOperation.add_conversation_line(
          conversation=conversation,
          chat_id=chat_id,
          role=entry["role"],
          line=entry["text"],
          system_prompt=system_prompt,
      )
    self.memory_provider.save_conversation(conversation)

    if CognitionOperation.should_reply(chat_type) and messages:
      reply = await self.language_provider.reply_in_conversation(messages)
      conversation, _ = MemoryOperation.add_conversation_line(
          conversation=conversation,
          chat_id=chat_id,
          role="assistant",
          line=reply,
          system_prompt=system_prompt,
      )
      self.memory_provider.save_conversation(conversation)
      if self._message_sender:
        await self._message_sender(chat_id, reply)

    self._cleanup_temp_files(batch)

  async def _perceive_message(self, msg: PendingMessage, chat_type: str) -> dict:
    if msg.media_type == "text":
      text = CognitionOperation.normalize_user_text(msg.text)
      sender = msg.user_info.get("first_name", "User")
      text = f"{sender}: {text}"
      return {"role": "system", "text": text}

    if msg.media_type == "voice":
      wav_path = await asyncio.to_thread(
          AudioOperation.convert_ogg_to_wav, Path(msg.audio_file_path))
      text = await self.audio_provider.speech_to_text(audio_file_path=wav_path)
      text = CognitionOperation.normalize_user_text(text)
      sender = msg.user_info.get("first_name", "User")
      text = f"{sender} (voice): {text}"
      if os.path.exists(wav_path):
        os.remove(wav_path)
      return {"role": "system", "text": text}

    if msg.media_type == "photo":
      descriptions = await asyncio.gather(
          *(self.vision_provider.image_to_description(p)
            for p in msg.photo_file_paths)
      )
      combined = "\n".join(
          f"[Photo {i+1}]: {desc}" for i, desc in enumerate(descriptions)
      )
      caption_part = f'with caption "{msg.caption}" ' if msg.caption else ""
      sender = msg.user_info.get("first_name", "User")
      line = f"{sender} sent {len(descriptions)} image(s) {caption_part}:\n{combined}"
      return {"role": "system", "text": line}

    raise ValueError(f"Unknown media type: {msg.media_type}")

  @staticmethod
  def _cleanup_temp_files(batch: list[PendingMessage]) -> None:
    for msg in batch:
      if msg.media_type == "voice" and msg.audio_file_path:
        if os.path.exists(msg.audio_file_path):
          os.remove(msg.audio_file_path)
      elif msg.media_type == "photo":
        for path in msg.photo_file_paths:
          if os.path.exists(path):
            os.remove(path)
