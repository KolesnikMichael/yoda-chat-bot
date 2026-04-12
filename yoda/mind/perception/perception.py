from __future__ import annotations

import asyncio
import os
from pathlib import Path

from yoda.mind.memory.data.pending_message import PendingMessage

from ..cognition import CognitionCore
from .audio import AudioCore, AudioProvider
from .vision import VisionProvider


class Perception:
    """Integration: orchestrates perception providers into perceived message lines."""

    def __init__(
        self,
        audio_provider: AudioProvider,
        vision_provider: VisionProvider,
    ):
        self._audio = audio_provider
        self._vision = vision_provider

    async def perceive_message(self, msg: PendingMessage) -> dict:
        text: str | None = None
        if msg.media_type == "text":
            text = CognitionCore.normalize_user_text(msg.text)
            sender = msg.user_info.get("first_name", "User")
            text = f'On {msg.timestamp} {sender} sent text message: "{text}"'

        if msg.media_type == "voice":
            wav_path = await asyncio.to_thread(
                AudioCore.convert_ogg_to_wav, Path(msg.audio_file_path))
            text = await self._audio.speech_to_text(audio_file_path=wav_path)
            text = CognitionCore.normalize_user_text(text)
            sender = msg.user_info.get("first_name", "User")
            text = f'On {msg.timestamp} {sender} sent voice message: "{text}"'
            if os.path.exists(wav_path):
                os.remove(wav_path)

        if msg.media_type == "photo":
            descriptions = await asyncio.gather(
                *(self._vision.image_to_description(p)
                  for p in msg.photo_file_paths)
            )
            combined = "\n".join(
                f"[Photo {i+1}]: {desc}" for i, desc in enumerate(descriptions)
            )
            caption_part = f' with caption "{msg.caption}"' if msg.caption else ""
            sender = msg.user_info.get("first_name", "User")
            text = (
                f"On {msg.timestamp} {sender} sent {len(descriptions)} image(s)"
                f"{caption_part}:\n{combined}"
            )

        if text is None:
            raise ValueError(f"Unknown media type: {msg.media_type}")
        return {
            "role": "system",
            "text": text,
            "timestamp": msg.timestamp,
            "message_id": msg.message_id,
            "user_id": msg.user_id,
        }
