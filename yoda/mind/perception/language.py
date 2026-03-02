class LanguageProvider:
  def __init__(self, settings: dict, llm_api):
    self._llm_api = llm_api
    self._model_name = settings["mistral_large_latest"]["model_name"]

  async def reply_in_conversation(self, conversation: list[dict]) -> str:
    return await self._llm_api.complete_chat_async(
        model_name=self._model_name,
        messages=conversation
    )
