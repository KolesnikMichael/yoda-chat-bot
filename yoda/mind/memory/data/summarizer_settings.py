from dataclasses import dataclass


@dataclass(frozen=True)
class SummarizerSettings:
    model_name: str
