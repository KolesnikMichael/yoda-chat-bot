from __future__ import annotations

import asyncio
import datetime as dtm
import logging
import os
from typing import TYPE_CHECKING

from yoda.mind.memory.data.pending_message import PendingMessage
from yoda.mind.data.routing_context import RoutingContext
from yoda.mind.agent.core.delivery_core import DeliveryCore
from yoda.mind.agent.core.outcome_core import OutcomeCore
from yoda.mind.agent.data.agent_data import AgentResult, RequestConstraints
from yoda.mind.agent.data.outcome_data import (
    SafeFailureCategory,
    StaticMessageDelivery,
    UserOperation,
)

from .affect import AffectCore, AffectProvider
from .cognition import CognitionCore, CognitionProvider
from .memory.memory import MemoryProvider
from .perception.language import LanguageProvider
from .perception.perception import Perception

if TYPE_CHECKING:
    from yoda.mind.agent.agent import Agent

logger = logging.getLogger(__name__)


class Mind:
    def __init__(
        self,
        language_provider: LanguageProvider,
        perception: Perception,
        memory_provider: MemoryProvider,
        affect_provider: AffectProvider,
        cognition_provider: CognitionProvider | None = None,
        agent: Agent | None = None,
        public_skill_descriptions: list[str] | None = None,
    ):
        self.language_provider = language_provider
        self.perception = perception
        self.memory_provider = memory_provider
        self.affect_provider = affect_provider
        self.cognition_provider = cognition_provider
        self.agent = agent
        self._message_sender = None
        self._capabilities_block = self._build_capabilities_block(
            public_skill_descriptions or [])
    @staticmethod
    def _build_capabilities_block(descriptions: list[str]) -> str:
        if not descriptions:
            return ""
        lines = ["\n== CAPABILITIES ==",
                 "You have these skills you can perform when asked:"]
        lines.extend(f"- {d}" for d in descriptions)
        lines.append(
            "If the user asks what you can do, describe these naturally in your voice.")
        lines.append(
            "When a delegated skill cannot complete the task, do not invent details, "
            "or offer improvised substitutes (e.g. text-only stand-ins for images). "
            "State briefly that it did not work this time; it may work another time."
        )
        return "\n".join(lines)

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
            *(self.memory_provider.update_sender_info(uid, uinfo)
              for uid, uinfo in unique_users.items()),
            self.memory_provider.update_chat_info(
                chat_id=chat_id, chat_type=chat_type, last_active=last_active),
        )

        perceived = await asyncio.gather(
            *(self.perception.perceive_message(msg) for msg in batch)
        )

        emotional_state = self.affect_provider.get_emotional_state()
        system_prompt = AffectCore.build_system_prompt(
            emotional_state, chat_type=chat_type) + self._capabilities_block
        conversation = self.memory_provider.get_conversation(chat_id=chat_id)

        messages = None
        for entry in perceived:
            conversation, messages = await self.memory_provider.append_conversation_line(
                conversation=conversation,
                chat_id=chat_id,
                kind="user",
                role=entry["role"],
                line=entry["text"],
                system_prompt=system_prompt,
                timestamp=entry["timestamp"],
                message_id=entry["message_id"],
                user_id=entry["user_id"],
            )
        self.memory_provider.save_conversation(conversation)

        routing = CognitionCore.build_routing_context(perceived, conversation)
        intent = await self._classify_intent(chat_id, routing)

        if intent == "agent_resume" and self.agent:
            await self._handle_agent_resume(
                chat_id, routing.current_user_text, system_prompt, conversation)

        elif intent == "agent_task" and self.agent:
            user_id = batch[0].user_id
            await self._handle_agent_task(
                chat_id, user_id, routing, system_prompt, conversation)

        elif intent == "chat" and CognitionCore.should_reply(chat_type) and messages:
            await self._reply_and_send(
                chat_id, messages, system_prompt, conversation)

        elif intent == "pass":
            logger.info(f"Intent is 'pass' for chat {chat_id}, skipping processing")

        self._cleanup_temp_files(batch)

    async def execute_scheduled_task(
        self,
        chat_id: int,
        user_id: int,
        skill_name: str,
        distilled_task: str,
        request_constraints: RequestConstraints | None = None,
    ) -> None:
        if not self.agent:
            logger.error("execute_scheduled_task called without agent")
            return

        profile = await self.memory_provider.get_user_profile(user_id, chat_id)
        result = await self.agent.run_with_skill(
            skill_name=skill_name,
            task=distilled_task,
            profile=profile,
            chat_id=chat_id,
            user_id=user_id,
            request_constraints=request_constraints or RequestConstraints(),
        )

        emotional_state = self.affect_provider.get_emotional_state()
        chat_type = CognitionCore.determine_chat_type(user_id, chat_id)
        system_prompt = AffectCore.build_system_prompt(
            emotional_state, chat_type=chat_type
        ) + self._capabilities_block
        conversation = self.memory_provider.get_conversation(chat_id=chat_id)
        await self._handle_agent_result(
            chat_id, result, system_prompt, conversation)

    async def notify_scheduled_failure(self, chat_id: int) -> None:
        emotional_state = self.affect_provider.get_emotional_state()
        chat_type = CognitionCore.determine_chat_type(0, chat_id)
        system_prompt = AffectCore.build_system_prompt(
            emotional_state, chat_type=chat_type
        )
        conversation = self.memory_provider.get_conversation(chat_id=chat_id)

        outcome = OutcomeCore.failure(
            UserOperation.REQUESTED_WORK,
            SafeFailureCategory.TRANSIENT,
        )
        await self._deliver_via_core(
            chat_id=chat_id,
            result=outcome,
            system_prompt=system_prompt,
            conversation=conversation,
        )

    async def deliver_scheduled_reminder(self, chat_id: int, user_id: int, reminder_text: str) -> None:
        emotional_state = self.affect_provider.get_emotional_state()
        chat_type = CognitionCore.determine_chat_type(user_id, chat_id)
        system_prompt = AffectCore.build_system_prompt(
            emotional_state, chat_type=chat_type)
        conversation = self.memory_provider.get_conversation(chat_id=chat_id)

        await self._deliver_via_core(
            chat_id=chat_id,
            result=StaticMessageDelivery(reminder_text=reminder_text),
            system_prompt=system_prompt,
            conversation=conversation,
        )

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
                        
    async def _classify_intent(
        self,
        chat_id: int,
        routing: RoutingContext,
    ) -> str:
        if not self.agent:
            return "chat"

        if await self.agent.has_pending_session(chat_id):
            return "agent_resume"

        if not routing.current_user_text or self.cognition_provider is None:
            return "chat"

        try:
            return await self.cognition_provider.classify_intent(routing)
        except Exception:
            logger.warning(
                "Intent classification failed, defaulting to chat", exc_info=True)
            return "chat"

    async def _handle_agent_task(
        self,
        chat_id: int,
        user_id: int,
        routing: RoutingContext,
        system_prompt: str,
        conversation,
    ) -> None:
        profile = await self.memory_provider.get_user_profile(user_id, chat_id)
        result = await self.agent.run(
            task=routing.current_user_text,
            profile=profile,
            chat_id=chat_id,
            user_id=user_id,
            recent_messages=routing.recent_messages,
        )
        await self._handle_agent_result(
            chat_id, result, system_prompt, conversation)

    async def _handle_agent_resume(
        self,
        chat_id: int,
        user_text: str,
        system_prompt: str,
        conversation,
    ) -> None:
        result = await self.agent.resume(chat_id, user_text)
        await self._handle_agent_result(
            chat_id, result, system_prompt, conversation)

    async def _handle_agent_result(
        self, chat_id: int, result: AgentResult, system_prompt: str, conversation,
    ) -> None:
        if result.clarification is not None:
            payload_source = result.clarification
        elif result.outcome is not None:
            payload_source = result.outcome
        else:
            return

        await self._deliver_via_core(
            chat_id=chat_id,
            result=payload_source,
            system_prompt=system_prompt,
            conversation=conversation,
        )

    async def _deliver_via_core(
        self,
        *,
        chat_id: int,
        result,
        system_prompt: str,
        conversation,
    ) -> None:
        payload = DeliveryCore.build_payload(result)
        utc_now = f"{dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"
        line = DeliveryCore.build_instruction(payload, current_time_utc=utc_now)

        conversation, messages = await self.memory_provider.append_message(
            conversation=conversation,
            chat_id=chat_id,
            kind="task_result",
            role="system",
            line=line,
            system_prompt=system_prompt,
            timestamp=f"{dtm.datetime.now(dtm.UTC)}",
        )
        self.memory_provider.save_conversation(conversation)

        if messages:
            await self._reply_and_send(
                chat_id, messages, system_prompt, conversation)

    async def _reply_and_send(
        self,
        chat_id: int,
        messages: list[dict],
        system_prompt: str,
        conversation,
    ) -> None:
        reply = await self.language_provider.reply_in_conversation(messages)
        reply_timestamp = f"{dtm.datetime.now(dtm.UTC)}"
        parts = CognitionCore.process_reply(reply)
        for part in parts:
            conversation, _ = await self.memory_provider.append_message(
                conversation=conversation,
                chat_id=chat_id,
                kind="assistant",
                role="assistant",
                line=part["text"],
                system_prompt=system_prompt,
                timestamp=reply_timestamp,
            )
            self.memory_provider.save_conversation(conversation)
            if self._message_sender:
                await self._message_sender(
                    chat_id,
                    part["text"],
                    reply_to_message_id=part["message_id"],
                )
