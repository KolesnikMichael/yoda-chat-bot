import json
import logging
from dataclasses import asdict

from yoda.api.storage_api import StorageApi
from yoda.mind.agent.data.agent_data import (
    AgentContext,
    AgentPhase,
    RequestConstraints,
    SkillSpec,
    SkillSummary,
)
from yoda.mind.agent.data.outcome_data import (
    JobKind,
    OutcomeEvidence,
    ResultKind,
    UserOperation,
)
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.migration import migrate

logger = logging.getLogger(__name__)

AGENT_SESSION_KEY = "agent_sessions"


class AgentSessionProvider:
    def __init__(self, storage_api: StorageApi):
        self._storage_api = storage_api

    async def save(self, context: AgentContext) -> None:
        data = {
            "task": context.task,
            "profile": asdict(context.profile),
            "chat_id": context.chat_id,
            "user_id": context.user_id,
            "catalog_summaries": [asdict(s) for s in context.catalog_summaries],
            "active_skill": asdict(context.active_skill) if context.active_skill else None,
            "messages": context.messages,
            "iteration": context.iteration,
            "tools_used": context.tools_used,
            "phase": context.phase.value,
            "selection_retry_used": context.selection_retry_used,
            "execution_retry_used": context.execution_retry_used,
            "protocol_version": context.protocol_version,
            "request_constraints": context.request_constraints.model_dump(),
            "outcome_evidence": [asdict(item) for item in context.outcome_evidence],
            "terminal_failure_pending": context.terminal_failure_pending,
        }
        await self._storage_api.hset(
            AGENT_SESSION_KEY, str(context.chat_id), json.dumps(data))
        logger.info(f"Saved agent session for chat {context.chat_id}")

    async def load(self, chat_id: int) -> AgentContext | None:
        raw = await self._storage_api.hget(AGENT_SESSION_KEY, str(chat_id))
        if raw is None:
            return None

        data = json.loads(raw)
        profile_data = migrate("user_profiles", data["profile"])
        profile = UserProfile(
            **{k: v for k, v in profile_data.items() if k in UserProfile.__dataclass_fields__}
        )
        catalog_summaries = [SkillSummary(**s) for s in data["catalog_summaries"]]
        active_skill = SkillSpec(**data["active_skill"]) if data["active_skill"] else None

        protocol_version = data.get("protocol_version", 1)
        selection_retry_used = bool(data.get("selection_retry_used", False))
        execution_retry_used = bool(data.get("execution_retry_used", False))
        if "phase" in data:
            phase = AgentPhase(data["phase"])
        elif active_skill is not None:
            phase = AgentPhase.EXECUTION
        else:
            phase = AgentPhase.SELECTION

        raw_constraints = data.get("request_constraints")
        if raw_constraints is None:
            request_constraints = RequestConstraints()
        else:
            request_constraints = RequestConstraints.model_validate(raw_constraints)

        outcome_evidence = [
            _decode_outcome_evidence(item)
            for item in data.get("outcome_evidence", [])
        ]

        return AgentContext(
            task=data["task"],
            profile=profile,
            chat_id=data["chat_id"],
            user_id=data.get("user_id", 0),
            catalog_summaries=catalog_summaries,
            active_skill=active_skill,
            messages=data.get("messages", []),
            iteration=data["iteration"],
            tools_used=data["tools_used"],
            phase=phase,
            selection_retry_used=selection_retry_used,
            execution_retry_used=execution_retry_used,
            request_constraints=request_constraints,
            protocol_version=protocol_version,
            outcome_evidence=outcome_evidence,
            terminal_failure_pending=bool(
                data.get("terminal_failure_pending", False),
            ),
        )

    async def has_session(self, chat_id: int) -> bool:
        raw = await self._storage_api.hget(AGENT_SESSION_KEY, str(chat_id))
        return raw is not None

    async def delete(self, chat_id: int) -> None:
        await self._storage_api.hdel(AGENT_SESSION_KEY, str(chat_id))
        logger.info(f"Deleted agent session for chat {chat_id}")


def _decode_outcome_evidence(raw: dict) -> OutcomeEvidence:
    job_kind_raw = raw.get("job_kind")
    scheduled_operation_raw = raw.get("scheduled_operation")
    return OutcomeEvidence(
        operation=UserOperation(raw["operation"]),
        result_kind=ResultKind(raw["result_kind"]),
        terminal=bool(raw["terminal"]),
        safe_summary=raw.get("safe_summary"),
        job_kind=JobKind(job_kind_raw) if job_kind_raw is not None else None,
        scheduled_operation=(
            UserOperation(scheduled_operation_raw)
            if scheduled_operation_raw is not None
            else None
        ),
        schedule=raw.get("schedule"),
    )
