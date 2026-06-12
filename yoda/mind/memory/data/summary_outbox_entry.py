from dataclasses import dataclass


@dataclass
class SummaryOutboxEntry:
    summary_id: str
    document: str
    created_at: float
    chunk_start_message_id: int
    chunk_end_message_id: int
    chunk_visible_count: int
    participants: list[int]
    skills: list[str]
    topics: list[str]
    added_at: str
