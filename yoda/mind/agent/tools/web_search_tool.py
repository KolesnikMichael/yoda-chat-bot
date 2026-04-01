import logging

from pydantic import BaseModel, Field

from yoda.api.tavily_api import TavilyApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class WebSearchParams(BaseModel):
    query: str
    search_depth: str = Field(
        default="basic",
        description='Search depth: "basic" or "advanced"',
    )
    topic: str = Field(
        default="general",
        description='Topic: "general", "news", or "finance"',
    )
    max_results: int = Field(default=5, ge=0, le=20)


class WebSearchTool(Tool):
    name = "web_search"
    parameters_schema = WebSearchParams

    def __init__(self, tavily_api: TavilyApi) -> None:
        self._tavily_api = tavily_api

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = WebSearchParams(**call.arguments)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        try:
            response = await self._tavily_api.search(
                params.query,
                max_results=params.max_results,
                search_depth=params.search_depth,
                topic=params.topic,
            )
        except Exception as e:
            logger.warning("web_search failed: %s", e, exc_info=True)
            return ToolResult(
                tool_name=self.name,
                output=f"Search failed: {e}",
                success=False,
            )

        output = self._format_response(params.query, response)
        return ToolResult(tool_name=self.name, output=output, success=True)

    @staticmethod
    def _format_response(query: str, response: dict) -> str:
        results = response.get("results") or []
        if not results:
            return f'No results found for "{query}".'

        lines: list[str] = [
            f'Found {len(results)} result(s) for "{query}":',
        ]
        for i, item in enumerate(results, start=1):
            title = item.get("title") or "(no title)"
            url = item.get("url") or ""
            content = (item.get("content") or "").strip()
            score = item.get("score")
            score_part = f" (score: {score:.2f})" if isinstance(score, (int, float)) else ""
            snippet = content[:500] + ("…" if len(content) > 500 else "")
            lines.append(f"{i}. [{title}]({url}){score_part} — {snippet}")

        return "\n".join(lines)
