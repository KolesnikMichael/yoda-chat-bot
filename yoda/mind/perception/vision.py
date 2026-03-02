import base64
import os


class VisionProvider:
  def __init__(self, settings: dict, llm_api):
    self._llm_api = llm_api
    self._model_name = settings["pixtral_large_latest"]["model_name"]

  @staticmethod
  def encode_image_to_base64(image_file_path) -> str:
    with open(image_file_path, "rb") as image_file:
      return base64.b64encode(image_file.read()).decode("utf-8")

  async def image_to_description(self, image_file_path: str) -> str:
    image_base64 = self.encode_image_to_base64(image_file_path)
    description = await self._llm_api.describe_image(
        model_name=self._model_name,
        image_base64=image_base64,
        prompt="Please describe the image in detail.",
    )
    if os.path.exists(image_file_path):
      os.remove(image_file_path)
    return description
