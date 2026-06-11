from dataclasses import dataclass, field, asdict


@dataclass
class UserProfile:
    preferred_name: str = ""
    gender: str = ""
    location: str = ""
    timezone: str = ""
    occupation: str = ""
    interests: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    skill_preferences: dict[str, list[str]] = field(default_factory=dict)
    schema_version: int = 2
    updated_on: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
