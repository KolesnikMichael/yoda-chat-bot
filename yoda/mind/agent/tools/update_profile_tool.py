import logging

from pydantic import BaseModel, Field

from yoda.mind.memory.memory import MemoryProvider
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)

ALLOWED_FIELDS = {
    "nickname", "preferred_language", "gender", "birthday", "age",
    "location", "timezone", "education", "occupation",
    "interests", "miscellaneous",
}


class UpdateProfileParams(BaseModel):
    fields: dict = Field(
        description="Dictionary of profile fields to update, "
        "e.g. {\"timezone\": \"Europe/Moscow\", \"location\": \"Saint Petersburg\"}"
    )


class UpdateProfileTool(Tool):
    name = "update_profile"
    parameters_schema = UpdateProfileParams

    def __init__(self, memory_provider: MemoryProvider):
        self._memory = memory_provider

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = UpdateProfileParams(**call.arguments)
        except Exception as e:
            logger.warning(f"update_profile: invalid params: {e}")
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        user_id = call.metadata.get("user_id")
        chat_id = call.metadata.get("chat_id")
        logger.info(f"update_profile: metadata user_id={user_id}, chat_id={chat_id}")
        if not user_id or not chat_id:
            logger.warning(f"update_profile: missing metadata, user_id={user_id}, chat_id={chat_id}")
            return ToolResult(
                tool_name=self.name,
                output="Missing user_id or chat_id in metadata",
                success=False,
            )

        unknown = set(params.fields.keys()) - ALLOWED_FIELDS
        if unknown:
            logger.warning(f"update_profile: unknown fields: {unknown}")
            return ToolResult(
                tool_name=self.name,
                output=f"Unknown profile fields: {', '.join(sorted(unknown))}",
                success=False,
            )

        await self._memory.update_user_profile(user_id, chat_id, params.fields)

        updated = ", ".join(f"{k}={v}" for k, v in params.fields.items())
        logger.info(f"Updated profile for user {user_id}@{chat_id}: {updated}")
        return ToolResult(
            tool_name=self.name,
            output=f"Profile updated: {updated}",
            success=True,
        )
