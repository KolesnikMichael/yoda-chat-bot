import json
import logging

from pydantic import BaseModel

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.data.outcome_data import ResultKind, TerminalResultFacts
from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.agent.tools.job_keys import ACTIVE_JOBS_KEY_PREFIX
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class DeleteUserDataParams(BaseModel):
    pass


class DeleteUserDataTool(Tool):
    name = "delete_user_data"
    parameters_schema = DeleteUserDataParams
    terminal = True

    def __init__(
        self,
        storage_api: StorageApi,
        scheduler_api: SchedulerApi,
        memory_provider: MemoryProvider,
    ):
        self._storage_api = storage_api
        self._scheduler_api = scheduler_api
        self._memory = memory_provider

    async def execute(self, call: ToolCall) -> ToolResult:
        user_id = call.metadata.get("user_id")
        if not user_id:
            return ToolResult(
                tool_name=self.name,
                output="Missing user_id in metadata",
                success=False,
            )

        deleted: dict[str, int] = {
            "user_record": 0,
            "profiles": 0,
            "jobs": 0,
            "private_chat": 0,
        }

        removed = await self._storage_api.hdel("users", str(user_id))
        if removed:
            deleted["user_record"] = 1

        all_profiles = await self._storage_api.hgetall("user_profiles")
        prefix = f"{user_id}@"
        for field_key in all_profiles:
            if field_key.startswith(prefix):
                await self._storage_api.hdel("user_profiles", field_key)
                deleted["profiles"] += 1

        job_keys = await self._storage_api.keys(f"{ACTIVE_JOBS_KEY_PREFIX}:*")
        for key in job_keys:
            entries = await self._storage_api.hgetall(key)
            for job_id, raw in entries.items():
                try:
                    meta = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if meta.get("user_id") == user_id:
                    self._scheduler_api.cancel(job_id)
                    await self._storage_api.hdel(key, job_id)
                    deleted["jobs"] += 1

        removed_chat = await self._storage_api.hdel("chats", str(user_id))
        if removed_chat:
            deleted["private_chat"] = 1

        self._memory.forget_conversation(user_id)

        parts = []
        if deleted["user_record"]:
            parts.append("user record")
        if deleted["profiles"]:
            parts.append(f"{deleted['profiles']} profile(s)")
        if deleted["jobs"]:
            parts.append(f"{deleted['jobs']} scheduled job(s)")
        if deleted["private_chat"]:
            parts.append("private chat metadata")

        if parts:
            summary = f"Deleted: {', '.join(parts)}."
        else:
            summary = "No data found to delete."

        logger.info(f"Deleted all data for user {user_id}: {deleted}")
        return ToolResult(
            tool_name=self.name,
            output=summary,
            success=True,
            terminal_facts=TerminalResultFacts(
                result_kind=ResultKind.USER_DATA,
                summary="User data deletion completed.",
            ),
        )
