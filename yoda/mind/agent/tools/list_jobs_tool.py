import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from yoda.api.storage_api import StorageApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.job_keys import active_jobs_key
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class ListJobsParams(BaseModel):
    pass


class ListJobsTool(Tool):
    name = "list_jobs"
    parameters_schema = ListJobsParams

    def __init__(self, storage_api: StorageApi):
        self._storage_api = storage_api

    async def execute(self, call: ToolCall) -> ToolResult:
        chat_id = call.metadata.get("chat_id")
        if chat_id is None:
            return ToolResult(
                tool_name=self.name,
                output="Missing chat_id in metadata",
                success=False,
            )

        key = active_jobs_key(chat_id)
        entries = await self._storage_api.hgetall(key)

        if not entries:
            return ToolResult(
                tool_name=self.name,
                output="No active jobs.",
                success=True,
            )

        lines: list[str] = []
        for job_id, raw in entries.items():
            meta = json.loads(raw)
            tz_name = meta.get("timezone", "UTC")
            kind = meta.get("kind", "message")
            schedule_type = meta.get("type", "?")
            description = meta.get("description", "")

            if schedule_type == "cron":
                cron_expr = meta.get("cron", "")
                timing = f"recurrence: {cron_expr}" if cron_expr else "recurrence: (cron)"
            else:
                deliver_utc = meta.get("deliver_at_utc", "") or ""
                display_time = deliver_utc
                try:
                    if deliver_utc:
                        utc_dt = datetime.fromisoformat(deliver_utc)
                        local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
                        display_time = local_dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, KeyError):
                    pass
                timing = f"scheduled: {display_time}"

            lines.append(
                f"- job_id: {job_id}, kind: {kind}, type: {schedule_type}, "
                f"description: \"{description}\", {timing}"
            )

        return ToolResult(
            tool_name=self.name,
            output=f"Active jobs ({len(lines)}):\n" + "\n".join(lines),
            success=True,
        )
