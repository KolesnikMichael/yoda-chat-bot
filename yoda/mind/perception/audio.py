from yoda.api.speech_api import SpeechApi


class AudioProvider:
  def __init__(self, speech_api: SpeechApi):
    self._speech_api = speech_api

  @classmethod
  def from_settings(cls, audio_settings: dict | None = None) -> "AudioProvider":
    # audio_settings reserved for future configuration (e.g. language, engine)
    speech_api = SpeechApi()
    return cls(speech_api=speech_api)

  async def speech_to_text(self, audio_file_path, language: str = "ru-RU") -> str:
    return await self._speech_api.speech_to_text(audio_file_path=audio_file_path, language=language)
