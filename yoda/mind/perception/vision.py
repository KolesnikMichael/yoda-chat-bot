import base64
from pathlib import Path
from typing import Protocol


class VisionChatBackend(Protocol):
    async def complete_chat_async(
        self, model_name: str, messages: list[dict]
    ) -> str:
        ...


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
    def __init__(self, settings: dict, chat_backend: VisionChatBackend) -> None:
        self._chat_backend = chat_backend
        try:
            self._model_name = settings["model_name"]
        except KeyError as e:
            raise ValueError(
                "Vision settings missing required 'model_name'") from e
        self._provider = settings.get("provider", "mistral")

    @staticmethod
    def encode_image_to_base64(image_file_path: str) -> str:
        with open(image_file_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _image_part(self, mime: str, image_base64: str) -> dict:
        data_url = f"data:{mime};base64,{image_base64}"
        if self._provider == "openrouter":
            return {
                "type": "image_url",
                "image_url": {"url": data_url},
            }
        return {
            "type": "image_url",
            "image_url": data_url,
        }

    async def image_to_description(self, image_file_path: str) -> str:
        image_base64 = self.encode_image_to_base64(image_file_path)
        mime = _mime_type_for_image_path(image_file_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Please describe the image in detail."},
                    self._image_part(mime, image_base64),
                ],
            }
        ]
        return await self._chat_backend.complete_chat_async(
            model_name=self._model_name,
            messages=messages,
        )
