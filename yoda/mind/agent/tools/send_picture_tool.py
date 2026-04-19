import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, Field

from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class SendPictureParams(BaseModel):
    file_path: str = Field(..., description="Local path to the image file from text_to_image")
    summary_for_chat: str = Field(
        ...,
        min_length=1,
        description=(
            "Detailed description of what is actually in the sent image, in the same language "
            "as the user's task — for the main chat model's context only (not sent to Telegram "
            "as a caption)."
        ),
    )


class SendPictureTool(Tool):
    name = "send_picture"
    parameters_schema = SendPictureParams
    terminal = True

    def __init__(
        self,
        send_photo: Callable[[int, str], Awaitable[None]],
    ) -> None:
        self._send_photo = send_photo

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = SendPictureParams(**call.arguments)
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
                output="Missing chat_id in tool metadata.",
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
            await self._send_photo(int(chat_id), str(path.resolve()))
        except Exception as e:
            logger.warning("send_picture Telegram failed: %s", e, exc_info=True)
            return ToolResult(
                tool_name=self.name,
                output=f"Failed to send photo: {e}",
                success=False,
            )

        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("send_picture could not delete cache file %s: %s", path, e)

        summary = params.summary_for_chat.strip()
        out = (
            "A photo was sent to the chat (no caption on the image). "
            f"Description: {summary}\n"
            "Keep this description in mind if the user discusses the image; do not read it "
            "verbatim to the user or paste the full text into chat."
        )
        return ToolResult(tool_name=self.name, output=out, success=True)
