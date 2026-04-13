from dataclasses import dataclass, field, asdict


@dataclass
class Chat:
    chat_type: str = ""
    history: list = field(default_factory=list)
    last_active: str = ""
    updated_on: str = ""
    schema_version: int = 4

    def to_dict(self) -> dict:
        return asdict(self)
