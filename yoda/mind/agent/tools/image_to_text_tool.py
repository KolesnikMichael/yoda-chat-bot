import logging
from pathlib import Path

from pydantic import BaseModel, Field

from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.perception.vision import VisionProvider

logger = logging.getLogger(__name__)


class ImageToTextParams(BaseModel):
    file_path: str = Field(
        ...,
        min_length=1,
        description=(
            "Local path to the image file (e.g. the path returned by text_to_image). "
            "Must be a readable image file on disk."
        ),
    )


class ImageToTextTool(Tool):
    name = "image_to_text"
    parameters_schema = ImageToTextParams

    def __init__(self, vision_provider: VisionProvider) -> None:
        self._vision = vision_provider

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = ImageToTextParams(**call.arguments)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        path = Path(params.file_path)
        if not path.is_file():
            return ToolResult(
                tool_name=self.name,
                output=f"File not found: {params.file_path}",
                success=False,
            )

        try:
            text = await self._vision.image_to_description(str(path.resolve()))
        except Exception as e:
            logger.warning("image_to_text vision failed: %s", e, exc_info=True)
            return ToolResult(
                tool_name=self.name,
                output=f"Vision failed: {e}",
                success=False,
            )

        stripped = (text or "").strip()
        if not stripped:
            return ToolResult(
                tool_name=self.name,
                output="Vision returned an empty description.",
                success=False,
            )

        return ToolResult(tool_name=self.name, output=stripped, success=True)
