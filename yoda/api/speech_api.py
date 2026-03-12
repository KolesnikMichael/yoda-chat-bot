import asyncio
from pathlib import Path


class SpeechApi:
    async def speech_to_text(self, audio_file_path: str | Path, language: str) -> str:
        return await asyncio.to_thread(self._speech_to_text_sync, Path(audio_file_path), language)

    def _speech_to_text_sync(self, audio_file_path: Path, language: str) -> str:
        import speech_recognition

        recognizer = speech_recognition.Recognizer()
        text = ""

        try:
            with speech_recognition.AudioFile(f"{audio_file_path}") as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(
                    audio_data, language=language)
        except speech_recognition.UnknownValueError:
            text = ""
        except speech_recognition.RequestError:
            text = ""

        return text
