from dataclasses import dataclass, field, asdict


@dataclass
class Chat:
    chat_type: str = ""
    users: list[int] = field(default_factory=list)
    history: list = field(default_factory=list)
    last_active: str = ""
    updated_on: str = ""
    schema_version: int = 3

    def to_dict(self) -> dict:
        return asdict(self)
