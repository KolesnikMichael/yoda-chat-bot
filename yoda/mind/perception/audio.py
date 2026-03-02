class AudioProvider:
  def __init__(self, speech_api):
    self._speech_api = speech_api

  async def speech_to_text(self, audio_file_path, language: str = "ru-RU") -> str:
    return await self._speech_api.speech_to_text(audio_file_path=audio_file_path, language=language)
