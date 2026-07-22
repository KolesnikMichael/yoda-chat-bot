"""Deterministic routing evaluation harness (TASK-020, test-only Integration)."""

from __future__ import annotations

import datetime as dtm
import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from yoda.mind.agent.data.agent_data import ToolCall
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.skills.catalog import SkillCatalog
from yoda.mind.agent.tools.ask_user_tool import AskUserTool
from yoda.mind.agent.tools.cancel_job_tool import CancelJobTool
from yoda.mind.agent.tools.delete_user_data_tool import DeleteUserDataTool
from yoda.mind.agent.tools.get_user_data_tool import GetUserDataTool
from yoda.mind.agent.tools.image_to_text_tool import ImageToTextTool
from yoda.mind.agent.tools.list_jobs_tool import ListJobsTool
from yoda.mind.agent.tools.schedule_message_tool import ScheduleMessageTool
from yoda.mind.agent.tools.schedule_task_tool import ScheduleTaskTool
from yoda.mind.agent.tools.send_picture_tool import SendPictureTool
from yoda.mind.agent.tools.text_to_image_tool import TextToImageTool
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.agent.tools.update_profile_tool import UpdateProfileTool
from yoda.mind.agent.tools.web_extract_tool import WebExtractTool
from yoda.mind.agent.tools.web_search_tool import WebSearchTool
from yoda.mind.evaluation.core import RoutingEvaluationCore
from yoda.mind.evaluation.data import (
    RoutingCase,
    RoutingCaseResult,
    RoutingCorpus,
    RoutingEvaluationReport,
    RoutingMessage,
    RoutingObservation,
    TurnObservation,
)
from yoda.mind.evaluation.observation import (
    ObservingAgent,
    ObservingCognitionProvider,
    ObservingMind,
)
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.pending_message import PendingMessage
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.perception.language import LanguageProvider
from yoda.mind.perception.perception import Perception

from tests.fakes import FakeAudioProvider, FakeVisionProvider
from tests.routing_evaluation.fakes import (
    InMemoryStorageApi,
    RecordedLLMApi,
    RecordedToolProvider,
)

PRODUCTION_SKILLS_DIR = (
    Path(__file__).resolve().parents[2] / "yoda" / "mind" / "agent" / "skills"
)


class _RecordedTool(Tool):
    def __init__(
        self,
        name: str,
        parameters_schema: type,
        provider: RecordedToolProvider,
        *,
        terminal: bool = False,
    ) -> None:
        self.name = name
        self.parameters_schema = parameters_schema
        self.terminal = terminal
        self._provider = provider

    async def execute(self, call: ToolCall):
        return await self._provider.execute(call)


class RoutingEvaluation:
    def __init__(self, skills_dir: Path = PRODUCTION_SKILLS_DIR) -> None:
        self._skills_dir = skills_dir
        self._catalog = SkillCatalog.load_catalog(skills_dir)
        self._public_descriptions = [
            summary.description
            for summary in SkillCatalog.public_summaries(self._catalog)
        ]

    async def run_case(self, case: RoutingCase) -> RoutingCaseResult:
        observation = await self._observe_case(case)
        return RoutingEvaluationCore.score_case(case, observation)

    async def _observe_case(self, case: RoutingCase) -> RoutingObservation:
        observation = RoutingObservation(case_id=case.id)
        storage = InMemoryStorageApi()
        memory = MemoryProvider(storage)
        chat_id = self._stable_id(case.id)
        user_id = chat_id
        for turn in case.turns:
            turn_obs = TurnObservation(turn_id=turn.id)
            observation.turns.append(turn_obs)
            with self._freeze_time(turn.fixed_now_utc):
                await self._run_turn(
                    case,
                    turn,
                    turn_obs,
                    storage=storage,
                    memory=memory,
                    chat_id=chat_id,
                    user_id=user_id,
                )
        return observation

    async def run_corpus(
        self,
        corpus: RoutingCorpus,
        *,
        case_id: str | None = None,
    ) -> RoutingEvaluationReport:
        cases = corpus.cases
        if case_id is not None:
            matches = [case for case in cases if case.id == case_id]
            if not matches:
                raise ValueError(f"unknown case id: {case_id}")
            cases = matches
        results = []
        for case in cases:
            results.append(await self.run_case(case))
        return RoutingEvaluationCore.aggregate(corpus.corpus_version, results)

    async def _run_turn(
        self,
        case: RoutingCase,
        turn,
        turn_obs: TurnObservation,
        *,
        storage: InMemoryStorageApi,
        memory: MemoryProvider,
        chat_id: int,
        user_id: int,
    ) -> None:
        recorded_llm = RecordedLLMApi(list(turn.model_responses))
        tool_provider = RecordedToolProvider(list(turn.tool_results))
        language_provider = LanguageProvider(
            {"model_name": "evaluation-model"},
            recorded_llm,
        )
        tools = self._build_tools(tool_provider, storage)
        session_provider = AgentSessionProvider(storage_api=storage)
        agent = ObservingAgent(
            language_provider=language_provider,
            tools=tools,
            skills_dir=self._skills_dir,
            session_provider=session_provider,
            turn_observation=turn_obs,
        )
        await memory.update_user_profile(
            user_id,
            chat_id,
            turn.profile.model_dump(),
        )
        self._seed_recent_messages(
            memory,
            chat_id=chat_id,
            recent_messages=turn.input.recent_messages,
        )
        perception = Perception(
            audio_provider=FakeAudioProvider(),
            vision_provider=FakeVisionProvider(),
        )
        cognition = ObservingCognitionProvider(
            language_provider=language_provider,
        )
        mind = ObservingMind(
            language_provider=language_provider,
            perception=perception,
            memory_provider=memory,
            affect_provider=_NoOpAffectProvider(),
            cognition_provider=cognition,
            agent=agent,
            public_skill_descriptions=self._public_descriptions,
            turn_observation=turn_obs,
        )
        if turn.event == "message":
            pending = PendingMessage(
                user_id=user_id,
                message_id=self._stable_id(f"{case.id}:{turn.id}"),
                user_info={"first_name": "EvalUser", "last_active": "now"},
                media_type="text",
                text=turn.input.text,
                timestamp=turn.fixed_now_utc.isoformat(),
            )
            await mind.process_message_batch(chat_id, [pending])
        elif turn.event == "resume":
            pending = PendingMessage(
                user_id=user_id,
                message_id=self._stable_id(f"{case.id}:{turn.id}"),
                user_info={"first_name": "EvalUser", "last_active": "now"},
                media_type="text",
                text=turn.input.text,
                timestamp=turn.fixed_now_utc.isoformat(),
            )
            await mind.process_message_batch(chat_id, [pending])
        elif turn.event == "scheduled_task":
            await mind.execute_scheduled_task(
                chat_id=chat_id,
                user_id=user_id,
                skill_name=turn.input.skill_name or "",
                distilled_task=turn.input.distilled_task or turn.input.text,
                request_constraints=turn.input.request_constraints,
            )
        recorded_llm.assert_fully_consumed()
        tool_provider.assert_fully_consumed()

    @staticmethod
    def _seed_recent_messages(
        memory: MemoryProvider,
        *,
        chat_id: int,
        recent_messages: list[RoutingMessage],
    ) -> None:
        if not recent_messages:
            return
        messages = [
            Message(
                role=item.role,
                kind="user" if item.role == "user" else "assistant",
                text=item.content,
                timestamp="2026-07-20T12:00:00+00:00",
            )
            for item in recent_messages
        ]
        memory.save_conversation(
            Conversation(
                chat_id=chat_id,
                messages=[
                    Message(role="system", kind="prompt", text="Reply as Yoda"),
                    *messages,
                ],
                introduced_users=set(),
            ),
        )

    @staticmethod
    def _stable_id(value: str) -> int:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") or 1

    def _build_tools(
        self,
        provider: RecordedToolProvider,
        storage: InMemoryStorageApi,
    ) -> list[Tool]:
        noop_memory = _NoOpMemoryWriter()
        noop_scheduler = _NoOpScheduler()
        noop_tavily = _NoOpTavily()
        noop_pixazo = _NoOpPixazo()
        noop_send = _NoOpSendPhoto()

        source_tools = [
            AskUserTool(),
            ScheduleMessageTool(scheduler_api=noop_scheduler, storage_api=storage),
            ScheduleTaskTool(
                scheduler_api=noop_scheduler,
                storage_api=storage,
                skills_dir=self._skills_dir,
            ),
            ListJobsTool(storage_api=storage),
            CancelJobTool(scheduler_api=noop_scheduler, storage_api=storage),
            UpdateProfileTool(memory_provider=noop_memory),
            WebSearchTool(tavily_api=noop_tavily),
            WebExtractTool(tavily_api=noop_tavily),
            GetUserDataTool(storage_api=storage),
            DeleteUserDataTool(
                storage_api=storage,
                scheduler_api=noop_scheduler,
                memory_provider=noop_memory,
            ),
            TextToImageTool(pixazo_api=noop_pixazo),
            ImageToTextTool(vision_provider=FakeVisionProvider()),
            SendPictureTool(send_photo=noop_send),
        ]
        return [
            _RecordedTool(
                tool.name,
                tool.parameters_schema,
                provider,
                terminal=getattr(tool, "terminal", False),
            )
            for tool in source_tools
        ]

    @staticmethod
    @contextmanager
    def _freeze_time(fixed_now: dtm.datetime) -> Iterator[None]:
        fixed = fixed_now
        if fixed.tzinfo is None:
            fixed = fixed.replace(tzinfo=dtm.UTC)

        class _FrozenDateTime(dtm.datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return fixed.replace(tzinfo=None)
                return fixed.astimezone(tz)

        with (
            patch("yoda.mind.mind.dtm.datetime", _FrozenDateTime),
            patch("yoda.mind.agent.agent.dtm.datetime", _FrozenDateTime),
        ):
            yield


class _NoOpAffectProvider:
    def get_emotional_state(self):
        from yoda.mind.memory.data.emotional_state import EmotionalState

        return EmotionalState()


class _NoOpMemoryWriter:
    async def update_user_profile(self, *args, **kwargs) -> None:
        return None


class _NoOpScheduler:
    async def schedule_job(self, *args, **kwargs) -> str:
        return "job-eval-1"

    async def cancel_job(self, *args, **kwargs) -> None:
        return None


class _NoOpTavily:
    async def search(self, *args, **kwargs) -> dict:
        return {"results": []}

    async def extract(self, *args, **kwargs) -> dict:
        return {"results": []}


class _NoOpPixazo:
    async def generate_image(self, *args, **kwargs) -> bytes:
        return b""


class _NoOpSendPhoto:
    async def __call__(self, *args, **kwargs) -> None:
        return None
