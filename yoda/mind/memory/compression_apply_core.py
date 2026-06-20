import datetime as dtm
import hashlib
import logging
from collections.abc import Callable

from yoda.mind.memory.compression_core import CompressionCore
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.inline_summary_envelope import InlineSummaryEnvelope
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.summary_outbox_entry import SummaryOutboxEntry
from yoda.mind.memory.memory import MemoryCore

logger = logging.getLogger(__name__)


class CompressionApplyCore:
    @staticmethod
    def slice_compressible_chunk(
        messages: list[Message],
        split: int,
    ) -> tuple[int, int, list[Message]]:
        chunk_start = 0
        if chunk_start < len(messages) and messages[chunk_start].kind == "prompt":
            chunk_start += 1
        while chunk_start < split and messages[chunk_start].kind == "summary":
            chunk_start += 1
        chunk_end = split
        return chunk_start, chunk_end, messages[chunk_start:chunk_end]

    @staticmethod
    def strip_user_introductions(
        chunk: list[Message],
    ) -> tuple[list[Message], set[int]]:
        removed_users: set[int] = set()
        stripped: list[Message] = []
        for message in chunk:
            if message.kind == "user_introduction":
                if message.user_id is not None:
                    removed_users.add(message.user_id)
                continue
            stripped.append(message)
        return stripped, removed_users

    @staticmethod
    def assert_removed_users_invariant(
        chunk: list[Message],
        removed_users: set[int],
    ) -> None:
        authors = {
            message.user_id
            for message in chunk
            if message.kind == "user" and message.user_id is not None
        }
        assert authors == removed_users, (
            f"removed_users invariant failed: authors={authors} removed_users={removed_users}"
        )

    @staticmethod
    def chunk_boundary_message_id(messages: list[Message], index: int) -> int:
        message = messages[index]
        if message.message_id is not None:
            return message.message_id
        return -index

    @staticmethod
    def compute_summary_id(
        chat_id: int,
        snapshot_ts: float,
        chunk_start_message_id: int,
        chunk_end_message_id: int,
    ) -> str:
        payload = f"{chat_id}:{snapshot_ts}:{chunk_start_message_id}:{chunk_end_message_id}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def visible_count(messages: list[Message]) -> int:
        return sum(1 for message in messages if CompressionCore.is_visible(message))

    @staticmethod
    def first_last_visible_timestamps(chunk: list[Message]) -> tuple[str, str]:
        visible = [message for message in chunk if CompressionCore.is_visible(message)]
        if not visible:
            return "", ""
        first_ts = visible[0].timestamp or ""
        last_ts = visible[-1].timestamp or ""
        return first_ts, last_ts

    @staticmethod
    def replace_chunk_with_summary(
        copy: Conversation,
        chunk_start: int,
        chunk_end: int,
        envelope: InlineSummaryEnvelope,
    ) -> None:
        summary_message = Message(
            role="system",
            kind="summary",
            text=envelope.to_message_text(),
        )
        copy.messages[chunk_start:chunk_end] = [summary_message]

    @staticmethod
    def evict_summaries_fifo(
        copy: Conversation,
        max_summary_count: int,
        snapshot_ts: float,
        summaries_added: int,
    ) -> tuple[list[SummaryOutboxEntry], list[dict[str, str]]]:
        summary_count = sum(1 for message in copy.messages if message.kind == "summary")
        excess = summary_count - max_summary_count
        if excess <= 0:
            return [], []

        to_evict = min(excess, summaries_added)
        outbox_entries: list[SummaryOutboxEntry] = []
        evicted_audit: list[dict[str, str]] = []
        evicted = 0
        scan_index = 0
        if scan_index < len(copy.messages) and copy.messages[scan_index].kind == "prompt":
            scan_index += 1

        while scan_index < len(copy.messages) and evicted < to_evict:
            message = copy.messages[scan_index]
            if message.kind != "summary":
                scan_index += 1
                continue

            envelope = InlineSummaryEnvelope.from_message_text(message.text)
            outbox_entries.append(
                SummaryOutboxEntry(
                    summary_id=envelope.summary_id,
                    document=envelope.text,
                    created_at=snapshot_ts,
                    chunk_start_message_id=0,
                    chunk_end_message_id=0,
                    chunk_visible_count=0,
                    participants=[],
                    skills=[],
                    topics=[],
                    added_at=envelope.added_at,
                )
            )
            evicted_audit.append({
                "summary_id": envelope.summary_id,
                "added_at": envelope.added_at,
            })
            del copy.messages[scan_index]
            evicted += 1

        return outbox_entries, evicted_audit

    @staticmethod
    def build_compression_audit_entry(
        snapshot_ts: float,
        summary_id: str,
        chunk_visible_count: int,
        from_ts: str,
        to_ts: str,
        evicted: list[dict[str, str]],
    ) -> dict:
        return {
            "ts": dtm.datetime.fromtimestamp(snapshot_ts, dtm.UTC).isoformat(),
            "event": "compression",
            "added": {
                "summary_id": summary_id,
                "visible_count": chunk_visible_count,
                "from_ts": from_ts,
                "to_ts": to_ts,
            },
            "evicted": evicted,
        }

    @staticmethod
    def apply_derived_fields(
        copy: Conversation,
        snapshot_ts: float,
        chunk_visible_count: int,
    ) -> None:
        copy.visible_messages -= chunk_visible_count
        copy.last_compressed_at = snapshot_ts

    @staticmethod
    def refresh_removed_users_on_copy(
        copy: Conversation,
        summary_insert_index: int,
        removed_users: set[int],
        intro_text_for_user_id: Callable[[int], str],
    ) -> None:
        tail_start = summary_insert_index + 1
        for user_id in removed_users:
            first_user_index: int | None = None
            for index in range(tail_start, len(copy.messages)):
                message = copy.messages[index]
                if message.kind == "user" and message.user_id == user_id:
                    first_user_index = index
                    break
            if first_user_index is not None:
                MemoryCore.ensure_user_introductions_in_range(
                    copy,
                    first_user_index,
                    first_user_index + 1,
                    intro_text_for_user_id,
                )
            else:
                copy.introduced_users.discard(user_id)

    @staticmethod
    def reconcile_arrivals_introductions(
        live: Conversation,
        copy_end_index: int,
        removed_users: set[int],
        intro_text_for_user_id: Callable[[int], str],
    ) -> None:
        arrivals_end = len(live.messages)

        for index in range(copy_end_index, arrivals_end):
            message = live.messages[index]
            if message.kind == "user_introduction" and message.user_id is not None:
                live.introduced_users.add(message.user_id)

        case_d_insertions: list[tuple[int, int]] = []
        seen_user_ids: set[int] = set()
        for index in range(copy_end_index, arrivals_end):
            message = live.messages[index]
            if message.kind != "user" or message.user_id is None:
                continue
            user_id = message.user_id
            if user_id in seen_user_ids:
                continue
            seen_user_ids.add(user_id)
            if user_id in live.introduced_users:
                continue
            has_intro = any(
                live.messages[j].kind == "user_introduction"
                and live.messages[j].user_id == user_id
                for j in range(copy_end_index, index)
            )
            if has_intro:
                live.introduced_users.add(user_id)
            elif user_id in removed_users:
                case_d_insertions.append((index, user_id))

        for index, user_id in sorted(case_d_insertions, key=lambda item: item[0], reverse=True):
            live.messages.insert(
                index,
                Message(
                    role="system",
                    kind="user_introduction",
                    text=intro_text_for_user_id(user_id),
                    user_id=user_id,
                ),
            )
            live.introduced_users.add(user_id)
