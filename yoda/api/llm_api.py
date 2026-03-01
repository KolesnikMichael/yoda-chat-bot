import asyncio
from mistralai import Mistral


class LLMApi:
  def __init__(self, api_key: str):
    self._client = Mistral(api_key=api_key)

  async def complete_chat_async(self, model_name: str, messages: list[dict]) -> str:
    response = await self._client.chat.complete_async(model=model_name, messages=messages)
    return response.choices[0].message.content

  async def describe_image(self, model_name: str, image_base64: str, prompt: str) -> str:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_base64}"},
            ],
        }
    ]
    response = await asyncio.to_thread(self._client.chat.complete, model=model_name, messages=messages)
    return response.choices[0].message.content
