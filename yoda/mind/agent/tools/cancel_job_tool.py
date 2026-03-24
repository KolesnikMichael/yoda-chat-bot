import logging

from pydantic import BaseModel

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.scheduler_tool import ACTIVE_JOBS_KEY_PREFIX
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class CancelJobParams(BaseModel):
    job_id: str


class CancelJobTool(Tool):
    name = "cancel_job"
    parameters_schema = CancelJobParams
    terminal = False

    def __init__(self, scheduler_api: SchedulerApi, storage_api: StorageApi):
        self._scheduler_api = scheduler_api
        self._storage_api = storage_api

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = CancelJobParams(**call.arguments)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        chat_id = call.metadata.get("chat_id")
        if chat_id is None:
            return ToolResult(
                tool_name=self.name,
                output="Missing chat_id in metadata",
                success=False,
            )

        scheduler_removed = self._scheduler_api.cancel(params.job_id)
        await self._storage_api.hdel(
            f"{ACTIVE_JOBS_KEY_PREFIX}:{chat_id}", params.job_id)

        if scheduler_removed:
            return ToolResult(
                tool_name=self.name,
                output=f"Job '{params.job_id}' cancelled successfully.",
                success=True,
            )

        return ToolResult(
            tool_name=self.name,
            output=f"Job '{params.job_id}' not found in scheduler (metadata cleaned up).",
            success=False,
        )
