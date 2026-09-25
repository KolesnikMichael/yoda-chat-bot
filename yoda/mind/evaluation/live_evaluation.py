"""Live-model routing evaluation Integration (TASK-021)."""

from __future__ import annotations

import datetime as dtm
import hashlib
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from yoda.api.chat_backend import ChatBackend
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
from yoda.mind.evaluation.corpus_provider import RoutingCorpusProvider
from yoda.mind.evaluation.data import (
    LiveCaseExclusion,
    LiveEvalReport,
    LiveRunStatus,
    OperationalErrorCategory,
    PromptIdentity,
    RoutingCase,
    RoutingCaseResult,
    RoutingMessage,
    RoutingObservation,
    TurnObservation,
)
from yoda.mind.evaluation.live_core import LiveRoutingEvaluationCore
from yoda.mind.evaluation.live_fakes import (
    FailOnCall,
    ForbiddenSideEffectError,
    InMemoryStorageApi,
    RecordedToolProvider,
    chroma_stub,
    media_stub,
    redis_stub,
    scheduler_stub,
    search_stub,
    telegram_stub,
)
from yoda.mind.evaluation.live_report_provider import LiveEvalReportProvider
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

logger = logging.getLogger(__name__)

DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "routing_evaluation"
    / "corpus-v1.json"
)
DEFAULT_REPORT_DIR = Path("artifacts/live_routing_eval")
PRODUCTION_SKILLS_DIR = (
    Path(__file__).resolve().parents[1] / "agent" / "skills"
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


class LiveRoutingEvaluation:
    def __init__(
        self,
        *,
        chat_backend: ChatBackend,
        model_name: str,
        skills_dir: Path = PRODUCTION_SKILLS_DIR,
        corpus_provider: RoutingCorpusProvider | None = None,
        report_provider: LiveEvalReportProvider | None = None,
    ) -> None:
        self._chat_backend = chat_backend
        self._model_name = model_name
        self._skills_dir = skills_dir
        self._catalog = SkillCatalog.load_catalog(skills_dir)
        self._public_descriptions = [
            summary.description
            for summary in SkillCatalog.public_summaries(self._catalog)
        ]
        self._corpus_provider = corpus_provider or RoutingCorpusProvider()
        self._report_provider = report_provider or LiveEvalReportProvider()
        self.last_artifact_path: Path | None = None

    async def run(
        self,
        corpus_path: Path,
        *,
        case_id: str | None = None,
        report_dir: Path | None = None,
    ) -> LiveEvalReport:
        started = dtm.datetime.now(dtm.UTC)
        run_id = uuid.uuid4().hex
        corpus = await self._corpus_provider.load(corpus_path)
        cases = list(corpus.cases)
        if case_id is not None:
            matches = [case for case in cases if case.id == case_id]
            if not matches:
                raise ValueError(f"unknown case id: {case_id}")
            cases = matches

        exclusions: list[LiveCaseExclusion] = []
        eligible: list[RoutingCase] = []
        for case in cases:
            exclusion = LiveRoutingEvaluationCore.live_eligibility(case)
            if exclusion is not None:
                exclusions.append(exclusion)
            else:
                eligible.append(case)

        case_results: list[RoutingCaseResult] = []
        incomplete_case_ids: list[str] = []
        unattempted_case_ids: list[str] = []
        operational_errors: list[OperationalErrorCategory] = []
        prompts_used: list[PromptIdentity] = []

        for case in eligible:
            try:
                observation = await self._observe_case(case, prompts_used)
                case_results.append(
                    RoutingEvaluationCore.score_case(case, observation),
                )
            except ForbiddenSideEffectError:
                incomplete_case_ids.append(case.id)
                operational_errors.append(
                    OperationalErrorCategory.FORBIDDEN_SIDE_EFFECT,
                )
                logger.warning(
                    "live eval forbidden side effect case_id=%s",
                    case.id,
                )
            except Exception as exc:
                incomplete_case_ids.append(case.id)
                category = self._map_provider_error(exc)
                operational_errors.append(category)
                logger.warning(
                    "live eval incomplete case_id=%s category=%s",
                    case.id,
                    category.value,
                )

        ended = dtm.datetime.now(dtm.UTC)
        status = self._run_status(
            case_results=case_results,
            incomplete_case_ids=incomplete_case_ids,
            eligible_count=len(eligible),
        )
        report = LiveRoutingEvaluationCore.build_report(
            run_id=run_id,
            started_at_utc=started,
            ended_at_utc=ended,
            status=status,
            corpus_schema_version=int(corpus.schema_version),
            corpus_version=corpus.corpus_version,
            case_filter=case_id,
            model_id=self._model_name,
            prompts_used=prompts_used,
            exclusions=exclusions,
            case_results=case_results,
            incomplete_case_ids=incomplete_case_ids,
            unattempted_case_ids=unattempted_case_ids,
            operational_errors=operational_errors,
        )
        artifact_dir = report_dir or DEFAULT_REPORT_DIR
        self.last_artifact_path = await self._report_provider.write(
            report,
            artifact_dir,
        )
        return report

    async def _observe_case(
        self,
        case: RoutingCase,
        prompts_used: list[PromptIdentity],
    ) -> RoutingObservation:
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
                    prompts_used=prompts_used,
                )
        return observation

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
        prompts_used: list[PromptIdentity],
    ) -> None:
        # Live decisions ignore recorded model_responses; tool fixtures remain.
        tool_provider = RecordedToolProvider(list(turn.tool_results))
        language_provider = LanguageProvider(
            {"model_name": self._model_name},
            self._chat_backend,
        )
        tools = self._build_tools(tool_provider, storage)
        session_provider = AgentSessionProvider(storage_api=storage)
        agent = ObservingAgent(
            language_provider=language_provider,
            tools=tools,
            skills_dir=self._skills_dir,
            session_provider=session_provider,
            turn_observation=turn_obs,
            prompt_sink=prompts_used,
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
            audio_provider=media_stub(),
            vision_provider=media_stub(),
        )
        cognition = ObservingCognitionProvider(
            language_provider=language_provider,
            prompt_sink=prompts_used,
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
            prompt_sink=prompts_used,
        )
        if turn.event in ("message", "resume"):
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
        tool_provider.assert_fully_consumed()

    def _build_tools(
        self,
        provider: RecordedToolProvider,
        storage: InMemoryStorageApi,
    ) -> list[Tool]:
        forbidden_memory = FailOnCall("memory_writer")
        forbidden_scheduler = scheduler_stub()
        forbidden_tavily = search_stub()
        forbidden_pixazo = media_stub()
        forbidden_send = telegram_stub()
        # Touch stubs so unused imports of redis/chroma remain referenced.
        _ = (redis_stub(), chroma_stub())

        source_tools = [
            AskUserTool(),
            ScheduleMessageTool(
                scheduler_api=forbidden_scheduler,
                storage_api=storage,
            ),
            ScheduleTaskTool(
                scheduler_api=forbidden_scheduler,
                storage_api=storage,
                skills_dir=self._skills_dir,
            ),
            ListJobsTool(storage_api=storage),
            CancelJobTool(
                scheduler_api=forbidden_scheduler,
                storage_api=storage,
            ),
            UpdateProfileTool(memory_provider=forbidden_memory),
            WebSearchTool(tavily_api=forbidden_tavily),
            WebExtractTool(tavily_api=forbidden_tavily),
            GetUserDataTool(storage_api=storage),
            DeleteUserDataTool(
                storage_api=storage,
                scheduler_api=forbidden_scheduler,
                memory_provider=forbidden_memory,
            ),
            TextToImageTool(pixazo_api=forbidden_pixazo),
            ImageToTextTool(vision_provider=media_stub()),
            SendPictureTool(send_photo=forbidden_send),
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

    @staticmethod
    def _map_provider_error(exc: Exception) -> OperationalErrorCategory:
        text = str(exc).lower()
        if "auth" in text or "unauthorized" in text or "api key" in text:
            return OperationalErrorCategory.PROVIDER_AUTH
        if "rate" in text and "limit" in text:
            return OperationalErrorCategory.PROVIDER_RATE_LIMIT
        if isinstance(exc, ForbiddenSideEffectError):
            return OperationalErrorCategory.FORBIDDEN_SIDE_EFFECT
        if "interrupt" in text:
            return OperationalErrorCategory.INTERRUPTED
        if any(token in text for token in ("provider", "http", "timeout", "connection")):
            return OperationalErrorCategory.PROVIDER_ERROR
        return OperationalErrorCategory.INTERNAL

    @staticmethod
    def _run_status(
        *,
        case_results: list[RoutingCaseResult],
        incomplete_case_ids: list[str],
        eligible_count: int,
    ) -> LiveRunStatus:
        if incomplete_case_ids and not case_results:
            return LiveRunStatus.FAILED
        if incomplete_case_ids or len(case_results) < eligible_count:
            return LiveRunStatus.PARTIAL
        return LiveRunStatus.COMPLETED

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
