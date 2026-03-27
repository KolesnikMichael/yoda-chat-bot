from __future__ import annotations

import asyncio
import datetime as dtm
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from yoda.mind.memory.data.pending_message import PendingMessage

from .affect import AffectCore, AffectProvider
from .cognition import CognitionCore, IntentClassification
from .memory.memory import MemoryCore, MemoryProvider
from .perception.audio import AudioCore, AudioProvider
from .perception.language import LanguageProvider
from .perception.vision import VisionProvider

if TYPE_CHECKING:
    from yoda.mind.agent.agent_provider import AgentProvider

logger = logging.getLogger(__name__)


class Mind:
    def __init__(
        self,
        language_provider: LanguageProvider,
        vision_provider: VisionProvider,
        audio_provider: AudioProvider,
        memory_provider: MemoryProvider,
        affect_provider: AffectProvider,
        agent_provider: AgentProvider | None = None,
    ):
        self.language_provider = language_provider
        self.vision_provider = vision_provider
        self.audio_provider = audio_provider
        self.memory_provider = memory_provider
        self.affect_provider = affect_provider
        self.agent_provider = agent_provider
        self._message_sender = None

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
                        
    async def _classify_intent(self, chat_id: int, perceived: list[dict]) -> str:
        if self.agent_provider and await self.agent_provider.has_pending_session(chat_id):
            return "agent_resume"

        if not self.agent_provider:
            return "chat"

        user_text = CognitionCore.extract_user_text(perceived)
        if not user_text:
            return "chat"

        try:
            intent_messages = CognitionCore.build_intent_messages(user_text)
            result = await self.language_provider.parse_structured(
                intent_messages, IntentClassification)
            logger.debug(f"Intent classification: '{user_text[:80]}' -> {result.intent}")
            if result.intent in ("agent_task", "chat"):
                return result.intent
        except Exception:
            logger.warning("Intent classification failed, defaulting to chat", exc_info=True)

        return "chat"

    async def _handle_chat_reply(
        self,
        chat_id: int,
        messages: list[dict],
        system_prompt: str,
        conversation,
    ) -> None:
        reply = await self.language_provider.reply_in_conversation(messages)
        reply_timestamp = f"{dtm.datetime.now(dtm.UTC)}"
        conversation, _ = MemoryCore.add_conversation_line(
            conversation=conversation,
            chat_id=chat_id,
            role="assistant",
            line=reply,
            system_prompt=system_prompt,
            timestamp=reply_timestamp,
        )
        self.memory_provider.save_conversation(conversation)
        if self._message_sender:
            await self._message_sender(chat_id, reply)

    async def _handle_agent_task(
        self,
        chat_id: int,
        user_id: int,
        user_text: str,
        system_prompt: str,
        conversation,
    ) -> None:
        profile = await self.memory_provider.get_user_profile(user_id, chat_id)
        result = await self.agent_provider.run(
            task=user_text, profile=profile, chat_id=chat_id, user_id=user_id)
        await self._handle_agent_result(
            chat_id, result, system_prompt, conversation)

    async def _handle_agent_resume(
        self,
        chat_id: int,
        user_text: str,
        system_prompt: str,
        conversation,
    ) -> None:
        result = await self.agent_provider.resume(chat_id, user_text)
        await self._handle_agent_result(
            chat_id, result, system_prompt, conversation)

    async def _handle_agent_result(
        self, chat_id: int, result, system_prompt: str, conversation,
    ) -> None:
        if result.clarification:
            line = f"Ask the user (rephrase naturally in your voice): {result.clarification}"
        elif result.answer:
            line = f"Agent completed a task. Result: {result.answer}. Communicate this to the user naturally"
        else:
            return

        line = f"{line}. Current time: {dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"

        conversation, messages = MemoryCore.add_conversation_line(
            conversation=conversation,
            chat_id=chat_id,
            role="system",
            line=line,
            system_prompt=system_prompt,
            timestamp=f"{dtm.datetime.now(dtm.UTC)}",
        )
        self.memory_provider.save_conversation(conversation)

        if messages:
            reply = await self.language_provider.reply_in_conversation(messages)
            conversation, _ = MemoryCore.add_conversation_line(
                conversation=conversation,
                chat_id=chat_id,
                role="assistant",
                line=reply,
                system_prompt=system_prompt,
                timestamp=f"{dtm.datetime.now(dtm.UTC)}",
            )
            self.memory_provider.save_conversation(conversation)
            if self._message_sender:
                await self._message_sender(chat_id, reply)

    async def _perceive_message(self, msg: PendingMessage, chat_type: str) -> dict:
        if msg.media_type == "text":
            text = CognitionCore.normalize_user_text(msg.text)
            sender = msg.user_info.get("first_name", "User")
            text = f'On {msg.timestamp} {sender} sent text message: "{text}"'

        if msg.media_type == "voice":
            wav_path = await asyncio.to_thread(
                AudioCore.convert_ogg_to_wav, Path(msg.audio_file_path))
            text = await self.audio_provider.speech_to_text(audio_file_path=wav_path)
            text = CognitionCore.normalize_user_text(text)
            sender = msg.user_info.get("first_name", "User")
            text = f'On {msg.timestamp} {sender} sent voice message: "{text}"'
            if os.path.exists(wav_path):
                os.remove(wav_path)

        if msg.media_type == "photo":
            descriptions = await asyncio.gather(
                *(self.vision_provider.image_to_description(p)
                  for p in msg.photo_file_paths)
            )
            combined = "\n".join(
                f"[Photo {i+1}]: {desc}" for i, desc in enumerate(descriptions)
            )
            caption_part = f' with caption "{msg.caption}" ' if msg.caption else ""
            sender = msg.user_info.get("first_name", "User")
            text = f"On {msg.timestamp} {sender} sent {len(descriptions)} image(s){caption_part}:\n{combined}"

        if text is None:
            raise ValueError(f"Unknown media type: {msg.media_type}")
        else:
            return {"role": "system", "text": text, "timestamp": msg.timestamp}

    def bind_message_sender(self, message_sender) -> None:
        self._message_sender = message_sender

    async def process_message_batch(self, chat_id: int, batch: list[PendingMessage]) -> None:
        if not batch:
            return

        chat_type = CognitionCore.determine_chat_type(
            batch[0].user_id, chat_id)

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
        system_prompt = AffectCore.build_system_prompt(
            emotional_state, chat_type=chat_type)
        conversation = self.memory_provider.get_conversation(chat_id=chat_id)

        messages = None
        for entry in perceived:
            conversation, messages = MemoryCore.add_conversation_line(
                conversation=conversation,
                chat_id=chat_id,
                role=entry["role"],
                line=entry["text"],
                system_prompt=system_prompt,
                timestamp=entry["timestamp"],
            )
        self.memory_provider.save_conversation(conversation)

        intent = await self._classify_intent(chat_id, perceived)

        if intent == "agent_resume" and self.agent_provider:
            user_text = CognitionCore.extract_user_text(perceived)
            await self._handle_agent_resume(
                chat_id, user_text, system_prompt, conversation)

        elif intent == "agent_task" and self.agent_provider:
            user_id = batch[0].user_id
            user_text = CognitionCore.extract_user_text(perceived)
            await self._handle_agent_task(
                chat_id, user_id, user_text, system_prompt, conversation)

        elif CognitionCore.should_reply(chat_type) and messages:
            await self._handle_chat_reply(
                chat_id, messages, system_prompt, conversation)

        self._cleanup_temp_files(batch)

    async def deliver_scheduled_reminder(self, chat_id: int, reminder_text: str) -> None:
        emotional_state = self.affect_provider.get_emotional_state()
        system_prompt = AffectCore.build_system_prompt(
            emotional_state, chat_type="private")
        conversation = self.memory_provider.get_conversation(chat_id=chat_id)

        line = f"SCHEDULED REMINDER for the user: {reminder_text}. Deliver this reminder naturally. Current time: {dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"
        conversation, messages = MemoryCore.add_conversation_line(
            conversation=conversation,
            chat_id=chat_id,
            role="system",
            line=line,
            system_prompt=system_prompt,
            timestamp=f"{dtm.datetime.now(dtm.UTC)}",
        )
        self.memory_provider.save_conversation(conversation)

        if messages:
            reply = await self.language_provider.reply_in_conversation(messages)
            conversation, _ = MemoryCore.add_conversation_line(
                conversation=conversation,
                chat_id=chat_id,
                role="assistant",
                line=reply,
                system_prompt=system_prompt,
                timestamp=f"{dtm.datetime.now(dtm.UTC)}",
            )
            self.memory_provider.save_conversation(conversation)
            if self._message_sender:
                await self._message_sender(chat_id, reply)
