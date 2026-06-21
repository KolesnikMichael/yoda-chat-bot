from dataclasses import dataclass


@dataclass
class SummaryOutboxEntry:
    summary_id: str
    document: str
    compressed_at: float
    content_from_ts: str
    content_to_ts: str
    skills: list[str]
    topics: list[str]
    added_at: str
