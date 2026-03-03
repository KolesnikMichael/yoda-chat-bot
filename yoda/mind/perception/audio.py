from yoda.api.speech_api import SpeechApi


class AudioProvider:
  def __init__(self, speech_api: SpeechApi, default_language: str = "ru-RU"):
    self._speech_api = speech_api
    self._default_language = default_language

  @classmethod
  def from_settings(cls, audio_settings: dict) -> "AudioProvider":
    try:
      default_language = audio_settings["default_language"]
    except KeyError as e:
      raise ValueError("Audio settings missing required 'default_language'") from e
    speech_api = SpeechApi()
    return cls(speech_api=speech_api, default_language=default_language)

  async def speech_to_text(self, audio_file_path, language: str | None = None) -> str:
    language = language or self._default_language
    return await self._speech_api.speech_to_text(audio_file_path=audio_file_path, language=language)
