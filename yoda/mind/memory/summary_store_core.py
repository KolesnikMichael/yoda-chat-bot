from typing import Protocol

from yoda.mind.memory.data.chroma_summary_record import ChromaSummaryRecord
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.summary_outbox_entry import SummaryOutboxEntry


class _ReadableSummaryRecord(Protocol):
    summary_id: str
    document: str
    embedding: list[float]


class SummaryStoreCore:
    @staticmethod
    def flatten_metadata(entry: SummaryOutboxEntry) -> dict[str, str | float]:
        return {
            "compressed_at": entry.compressed_at,
            "content_from_ts": entry.content_from_ts,
            "content_to_ts": entry.content_to_ts,
            "skills": ",".join(entry.skills),
            "topics": ",".join(entry.topics),
        }

    @staticmethod
    def outbox_entries_to_records(
        entries: list[SummaryOutboxEntry],
        embeddings: list[list[float]],
    ) -> list[ChromaSummaryRecord]:
        if len(entries) != len(embeddings):
            raise ValueError(
                f"entries/embeddings length mismatch: {len(entries)} vs {len(embeddings)}"
            )
        return [
            ChromaSummaryRecord(
                summary_id=entry.summary_id,
                document=entry.document,
                embedding=embedding,
                compressed_at=entry.compressed_at,
                content_from_ts=entry.content_from_ts,
                content_to_ts=entry.content_to_ts,
                skills=list(entry.skills),
                topics=list(entry.topics),
            )
            for entry, embedding in zip(entries, embeddings, strict=True)
        ]

    @staticmethod
    def pending_outbox_ids(conversations: list[Conversation]) -> set[str]:
        ids: set[str] = set()
        for conversation in conversations:
            for entry in conversation.pending_vectorization:
                ids.add(entry.summary_id)
        return ids

    @staticmethod
    def is_complete_record(
        record: _ReadableSummaryRecord,
        *,
        expected_dimension: int,
    ) -> bool:
        return bool(record.document) and len(record.embedding) == expected_dimension

    @staticmethod
    def incomplete_ids_to_delete(
        records: list[_ReadableSummaryRecord],
        pending_outbox_ids: set[str],
        *,
        expected_dimension: int,
    ) -> list[str]:
        to_delete: list[str] = []
        for record in records:
            if SummaryStoreCore.is_complete_record(
                record,
                expected_dimension=expected_dimension,
            ):
                continue
            if record.summary_id in pending_outbox_ids:
                continue
            to_delete.append(record.summary_id)
        return to_delete
