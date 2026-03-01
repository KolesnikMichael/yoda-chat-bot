import asyncio
import os
from pathlib import Path


class SpeechApi:
  async def speech_to_text(self, audio_file_path: str | Path, language: str) -> str:
    return await asyncio.to_thread(self._speech_to_text_sync, Path(audio_file_path), language)

  def _speech_to_text_sync(self, audio_file_path: Path, language: str) -> str:
    import speech_recognition
    from pydub import AudioSegment

    project_root = Path(__file__).resolve().parents[2]
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    local_ffmpeg = project_root / "bin" / ffmpeg_name
    if local_ffmpeg.exists():
      AudioSegment.converter = str(local_ffmpeg)

    wav_audio_file_path = audio_file_path.with_suffix(".wav")
    audio = AudioSegment.from_file(audio_file_path, format="ogg")
    audio.export(wav_audio_file_path, format="wav")

    recognizer = speech_recognition.Recognizer()
    text = ""

    try:
      with speech_recognition.AudioFile(f"{wav_audio_file_path}") as source:
        audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language=language)
    except speech_recognition.UnknownValueError:
      text = ""
    except speech_recognition.RequestError:
      text = ""
    finally:
      if os.path.exists(audio_file_path):
        os.remove(audio_file_path)
      if os.path.exists(wav_audio_file_path):
        os.remove(wav_audio_file_path)

    return text
