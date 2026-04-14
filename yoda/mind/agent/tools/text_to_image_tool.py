import logging
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from yoda.api.pixazo_api import PixazoApi
from yoda.api.telegram_api import FILE_CACHE_DIR
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class TextToImageParams(BaseModel):
    english_prompt: str = Field(
        ...,
        min_length=1,
        description=(
            "Single concise English prompt for the diffusion model: scene, subjects, "
            "style, lighting. The executor must translate/normalize from the user's task."
        ),
    )


class TextToImageTool(Tool):
    name = "text_to_image"
    parameters_schema = TextToImageParams

    def __init__(self, pixazo_api: PixazoApi) -> None:
        self._pixazo = pixazo_api

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = TextToImageParams(**call.arguments)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        english = params.english_prompt.strip()
        logger.debug("text_to_image english prompt (truncated): %s...", english[:200])

        try:
            image_bytes = await self._pixazo.generate_image_bytes(english)
        except Exception as e:
            logger.warning("text_to_image Pixazo failed: %s", e, exc_info=True)
            return ToolResult(
                tool_name=self.name,
                output=f"Image generation failed: {e}",
                success=False,
            )

        cache_dir = Path(FILE_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = cache_dir / f"gen_{uuid.uuid4().hex}.png"
        out_path.write_bytes(image_bytes)

        return ToolResult(
            tool_name=self.name,
            output=str(out_path.resolve()),
            success=True,
        )
