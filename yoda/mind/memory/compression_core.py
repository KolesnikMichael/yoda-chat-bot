import datetime as dtm
from typing import Literal

from .data.chat_compression_settings import ChatCompressionSettings
from .data.message import Message

_VISIBLE_KINDS = frozenset({"user", "assistant"})

ChatType = Literal["private", "group"]


class CompressionCore:
    @staticmethod
    def is_visible(message: Message) -> bool:
        return message.kind in _VISIBLE_KINDS

    @staticmethod
    def parse_message_timestamp(timestamp: str) -> float:
        if not timestamp:
            return 0.0
        normalized = timestamp.replace("Z", "+00:00")
        if " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T", 1)
        try:
            return dtm.datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _resolve_chat_type(chat_type: str) -> ChatType:
        if chat_type == "private":
            return "private"
        if chat_type == "group":
            return "group"
        raise ValueError(f"Unknown chat_type: {chat_type!r}")

    @staticmethod
    def gap_threshold_seconds(
        settings: ChatCompressionSettings,
        chat_type: str,
        tick_seconds: float,
    ) -> float:
        resolved = CompressionCore._resolve_chat_type(chat_type)
        quiet_runs = (
            settings.quiet_runs_before_compression.private
            if resolved == "private"
            else settings.quiet_runs_before_compression.group
        )
        return quiet_runs * settings.gap_to_trigger_ratio * tick_seconds

    @staticmethod
    def align_boundary(messages: list[Message], split_index: int) -> int:
        for index in range(split_index, len(messages)):
            if messages[index].kind == "user":
                return index
        return len(messages)

    @staticmethod
    def select_size_trigger_window(messages: list[Message]) -> int | None:
        visible_indices = [
            index
            for index, message in enumerate(messages)
            if CompressionCore.is_visible(message)
        ]
        total_visible = len(visible_indices)
        if total_visible == 0:
            return None

        k = total_visible // 2
        if k == 0:
            return None

        candidate = visible_indices[k]
        split = CompressionCore.align_boundary(messages, candidate)
        if split <= 0 or split >= len(messages):
            return None
        return split

    @staticmethod
    def select_timeout_trigger_window(
        messages: list[Message],
        settings: ChatCompressionSettings,
        chat_type: str,
        tick_seconds: float,
    ) -> int | None:
        gap_threshold = CompressionCore.gap_threshold_seconds(
            settings, chat_type, tick_seconds
        )
        visible_indices = [
            index
            for index, message in enumerate(messages)
            if CompressionCore.is_visible(message)
        ]
        if len(visible_indices) < settings.min_chunk_length:
            return None

        for pair_end in range(len(visible_indices) - 1, 0, -1):
            older_idx = visible_indices[pair_end - 1]
            newer_idx = visible_indices[pair_end]
            delta = (
                CompressionCore.parse_message_timestamp(
                    messages[newer_idx].timestamp
                )
                - CompressionCore.parse_message_timestamp(
                    messages[older_idx].timestamp
                )
            )
            if delta <= gap_threshold:
                continue

            candidate = older_idx + 1
            tail_visible = sum(
                1 for index in visible_indices if index >= candidate
            )
            if tail_visible < settings.min_chunk_length:
                continue

            split = CompressionCore.align_boundary(messages, candidate)
            if split <= 0 or split >= len(messages):
                continue
            return split

        return None

    @staticmethod
    def should_fire_size_trigger(
        visible_messages: int,
        settings: ChatCompressionSettings,
    ) -> bool:
        return visible_messages > settings.size_trigger_threshold

    @staticmethod
    def passes_timeout_entry_guard(
        visible_messages: int,
        settings: ChatCompressionSettings,
    ) -> bool:
        return visible_messages > 2 * settings.min_chunk_length

    @staticmethod
    def is_quiet_for_n_runs(
        last_visible_at: float,
        now: float,
        settings: ChatCompressionSettings,
        chat_type: str,
        tick_seconds: float,
    ) -> bool:
        resolved = CompressionCore._resolve_chat_type(chat_type)
        quiet_runs = (
            settings.quiet_runs_before_compression.private
            if resolved == "private"
            else settings.quiet_runs_before_compression.group
        )
        return now - last_visible_at >= quiet_runs * tick_seconds

    @staticmethod
    def has_visible_activity_since_compression(
        last_visible_at: float,
        last_compressed_at: float,
    ) -> bool:
        return last_visible_at > last_compressed_at

    @staticmethod
    def should_evaluate_timeout_trigger(
        visible_messages: int,
        last_visible_at: float,
        last_compressed_at: float,
        now: float,
        settings: ChatCompressionSettings,
        chat_type: str,
        tick_seconds: float,
    ) -> bool:
        return (
            CompressionCore.passes_timeout_entry_guard(visible_messages, settings)
            and CompressionCore.is_quiet_for_n_runs(
                last_visible_at, now, settings, chat_type, tick_seconds
            )
            and CompressionCore.has_visible_activity_since_compression(
                last_visible_at, last_compressed_at
            )
        )
