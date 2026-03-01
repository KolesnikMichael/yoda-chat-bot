from dataclasses import dataclass, field


@dataclass
class UserProfile:
  nickname: str = ""
  preferred_language: str = ""
  gender: str = ""
  birthday: str = ""
  age: str = ""
  location: str = ""
  timezone: str = ""
  education: str = ""
  occupation: str = ""
  interests: list[str] = field(default_factory=list)
  miscellaneous: list[str] = field(default_factory=list)
  schema_version: int = 1
  updated_on: str = ""
