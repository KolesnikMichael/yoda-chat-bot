import json
import logging

from pydantic import BaseModel

from yoda.api.storage_api import StorageApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.job_keys import ACTIVE_JOBS_KEY_PREFIX
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class GetUserDataParams(BaseModel):
    pass


class GetUserDataTool(Tool):
    name = "get_user_data"
    parameters_schema = GetUserDataParams

    def __init__(self, storage_api: StorageApi):
        self._storage_api = storage_api

    async def execute(self, call: ToolCall) -> ToolResult:
        user_id = call.metadata.get("user_id")
        if not user_id:
            return ToolResult(
                tool_name=self.name,
                output="Missing user_id in metadata",
                success=False,
            )

        sections: list[str] = []

        user_raw = await self._storage_api.hget("users", str(user_id))
        if user_raw:
            sections.append(f"## User record\n{user_raw}")

        chat_raw = await self._storage_api.hget("chats", str(user_id))
        if chat_raw:
            sections.append(f"## Private chat metadata\n{chat_raw}")

        all_profiles = await self._storage_api.hgetall("user_profiles")
        prefix = f"{user_id}@"
        user_profiles = {k: v for k, v in all_profiles.items()
                         if k.startswith(prefix)}
        if user_profiles:
            lines = [f"## Profiles ({len(user_profiles)})"]
            for field_key, raw in user_profiles.items():
                chat_id = field_key[len(prefix):]
                lines.append(f"- chat {chat_id}: {raw}")
            sections.append("\n".join(lines))

        job_keys = await self._storage_api.keys(f"{ACTIVE_JOBS_KEY_PREFIX}:*")
        user_jobs: list[str] = []
        for key in job_keys:
            entries = await self._storage_api.hgetall(key)
            for job_id, raw in entries.items():
                try:
                    meta = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if meta.get("user_id") == user_id:
                    chat_id = key.split(":", 1)[1] if ":" in key else "?"
                    user_jobs.append(
                        f"- job_id: {job_id}, chat: {chat_id}, "
                        f"description: \"{meta.get('description', '')}\", "
                        f"scheduled: {meta.get('deliver_at_utc', '?')}"
                    )
        if user_jobs:
            sections.append(
                f"## Active jobs ({len(user_jobs)})\n" + "\n".join(user_jobs))

        if not sections:
            return ToolResult(
                tool_name=self.name,
                output="No data found for this user.",
                success=True,
            )

        return ToolResult(
            tool_name=self.name,
            output="\n\n".join(sections),
            success=True,
        )
