from dataclasses import dataclass


@dataclass(frozen=True)
class SummarizerResult:
    summary: str
    topics: list[str]
    participants: list[int]
    skills: list[str]
    profile_updates: dict[int, dict]
