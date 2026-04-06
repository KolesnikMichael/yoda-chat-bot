from dataclasses import dataclass, asdict


@dataclass
class User:
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    last_active: str = ""
    known_since: str = ""
    schema_version: int = 2

    def to_dict(self) -> dict:
        return asdict(self)
