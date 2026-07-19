from dataclasses import dataclass


@dataclass(frozen=True)
class ChromaSummaryRecord:
    summary_id: str
    document: str
    embedding: list[float]
    compressed_at: float
    content_from_ts: str
    content_to_ts: str
    skills: list[str]
    topics: list[str]
