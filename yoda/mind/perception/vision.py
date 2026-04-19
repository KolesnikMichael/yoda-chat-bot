import base64
from pathlib import Path

from yoda.api.llm_api import LLMApi


def _mime_type_for_image_path(image_file_path: str) -> str:
    suf = Path(image_file_path).suffix.lower()
    if suf == ".png":
        return "image/png"
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".webp":
        return "image/webp"
    if suf == ".gif":
        return "image/gif"
    return "image/jpeg"


class VisionProvider:
    def __init__(self, settings: dict, llm_api: LLMApi):
        self._llm_api = llm_api
        try:
            self._model_name = settings["model_name"]
        except KeyError as e:
            raise ValueError(
                "Vision settings missing required 'model_name'") from e

    @staticmethod
    def encode_image_to_base64(image_file_path: str) -> str:
        with open(image_file_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def image_to_description(self, image_file_path: str) -> str:
        image_base64 = self.encode_image_to_base64(image_file_path)
        mime = _mime_type_for_image_path(image_file_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Please describe the image in detail."},
                    {
                        "type": "image_url",
                        "image_url": f"data:{mime};base64,{image_base64}",
                    },
                ],
            }
        ]
        return await self._llm_api.complete_chat_via_thread(
            model_name=self._model_name,
            messages=messages,
        )
