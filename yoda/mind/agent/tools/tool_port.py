from abc import ABC, abstractmethod

from pydantic import BaseModel

from yoda.mind.agent.data.agent_data import ToolCall, ToolResult


class Tool(ABC):
    name: str
    parameters_schema: type[BaseModel]
    terminal: bool = False

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        ...

    def describe(self) -> dict:
        """Auto-generate tool description from Pydantic schema for LLM context."""
        schema = self.parameters_schema.model_json_schema()
        return {
            "name": self.name,
            "parameters": {
                k: v for k, v in schema.get("properties", {}).items()
            },
            "required": schema.get("required", []),
        }
