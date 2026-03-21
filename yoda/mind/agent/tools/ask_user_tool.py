from pydantic import BaseModel

from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool


class AskUserParams(BaseModel):
    question: str


class AskUserTool(Tool):
    name = "ask_user"
    parameters_schema = AskUserParams

    async def execute(self, call: ToolCall) -> ToolResult:
        params = AskUserParams(**call.arguments)
        return ToolResult(
            tool_name=self.name,
            output=params.question,
            success=True,
            suspend=True,
        )
