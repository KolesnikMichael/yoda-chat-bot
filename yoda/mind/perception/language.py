from yoda.api.llm_api import LLMApi


class LanguageProvider:
  def __init__(self, settings: dict, llm_api: LLMApi):
    self._llm_api = llm_api
    self._model_name = settings["mistral_large_latest"]["model_name"]

  @classmethod
  def from_settings(cls, language_settings: dict) -> "LanguageProvider":
    api_key = language_settings["mistral_large_latest"]["api_key"]
    llm_api = LLMApi(api_key=api_key)
    return cls(settings=language_settings, llm_api=llm_api)

  async def reply_in_conversation(self, conversation: list[dict]) -> str:
    return await self._llm_api.complete_chat_async(
        model_name=self._model_name,
        messages=conversation,
    )
