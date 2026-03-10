from dataclasses import dataclass, field


@dataclass
class PendingMessage:
  user_id: int
  user_info: dict
  media_type: str
  text: str = ""
  photo_file_paths: list[str] = field(default_factory=list)
  caption: str = ""
  audio_file_path: str = ""
  media_group_id: str | None = None
  timestamp: str = ""
