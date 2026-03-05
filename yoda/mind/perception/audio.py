import os
from pathlib import Path

from pydub import AudioSegment  # type: ignore[reportMissingImports]

from yoda.api.speech_api import SpeechApi


class AudioOperation:
  @staticmethod
  def convert_ogg_to_wav(audio_file_path: Path) -> Path:
    project_root = Path(__file__).resolve().parents[3]
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    local_ffmpeg = project_root / "bin" / ffmpeg_name
    if local_ffmpeg.exists():
      AudioSegment.converter = str(local_ffmpeg)

    wav_audio_file_path = audio_file_path.with_suffix(".wav")
    audio = AudioSegment.from_file(audio_file_path, format="ogg")
    audio.export(wav_audio_file_path, format="wav")
    return wav_audio_file_path


class AudioProvider:
  def __init__(self, speech_api: SpeechApi, default_language: str = "ru-RU"):
    self._speech_api = speech_api
    self._default_language = default_language

  async def speech_to_text(self, audio_file_path: str | Path, language: str | None = None) -> str:
    language = language or self._default_language
    return await self._speech_api.speech_to_text(audio_file_path=audio_file_path, language=language)
