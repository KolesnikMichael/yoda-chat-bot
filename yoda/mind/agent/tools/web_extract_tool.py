import logging

from pydantic import BaseModel, Field

from yoda.api.tavily_api import TavilyApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)

_CONTENT_MAX_CHARS = 2000


class WebExtractParams(BaseModel):
    urls: list[str] = Field(
        ...,
        min_length=1,
        description="One or more URLs to extract content from (max 20 per Tavily API).",
    )


class WebExtractTool(Tool):
    name = "web_extract"
    parameters_schema = WebExtractParams
    terminal = False

    def __init__(self, tavily_api: TavilyApi) -> None:
        self._tavily_api = tavily_api

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = WebExtractParams(**call.arguments)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        if len(params.urls) > 20:
            return ToolResult(
                tool_name=self.name,
                output="At most 20 URLs are allowed per request.",
                success=False,
            )

        try:
            response = await self._tavily_api.extract(params.urls)
        except Exception as e:
            logger.warning("web_extract failed: %s", e, exc_info=True)
            return ToolResult(
                tool_name=self.name,
                output=f"Extract failed: {e}",
                success=False,
            )

        output = self._format_response(response)
        return ToolResult(tool_name=self.name, output=output, success=True)

    @staticmethod
    def _format_response(response: dict) -> str:
        ok_results = response.get("results") or []
        failed = response.get("failed_results") or []

        parts: list[str] = []

        for item in ok_results:
            url = item.get("url") or ""
            raw = (item.get("raw_content") or "").strip()
            if len(raw) > _CONTENT_MAX_CHARS:
                raw = raw[:_CONTENT_MAX_CHARS] + "…"
            parts.append(f"### {url}\n{raw if raw else '(empty content)'}")

        if failed:
            parts.append("### Failed URLs")
            for f in failed:
                fu = f.get("url") if isinstance(f, dict) else str(f)
                err = f.get("error", "unknown error") if isinstance(f, dict) else ""
                parts.append(f"- {fu}: {err}")

        if not parts:
            return "No content extracted."

        return "\n\n".join(parts)
