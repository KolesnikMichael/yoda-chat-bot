import logging
import os
import speech_recognition
from pydub import AudioSegment

logger = logging.getLogger(__name__)


class SpeechRecognizer:
  def __init__(self):
    pass

  def speech_to_text(self, audio_file_path, language: str):
    wav_audio_file_path = audio_file_path.with_suffix(".wav")

    audio = AudioSegment.from_file(audio_file_path, format="ogg")
    audio.export(wav_audio_file_path, format="wav")

    recognizer = speech_recognition.Recognizer()
    text = ""

    try:
      with speech_recognition.AudioFile(f"{wav_audio_file_path}") as source:
        audio_data = recognizer.record(source)
        text = recognizer.recognize_google(
            audio_data, language=language)
    except speech_recognition.UnknownValueError:
      logger.error("Could not recognize speech in audio")
    except speech_recognition.RequestError as e:
      logger.error("Speech recognition service unavailalbe")
    finally:
      os.remove(audio_file_path)
      os.remove(wav_audio_file_path)
    return text
