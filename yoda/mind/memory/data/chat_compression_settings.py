from dataclasses import dataclass


@dataclass
class QuietRunsSettings:
    private: int
    group: int


@dataclass
class ChatCompressionSettings:
    size_trigger_threshold: int
    min_chunk_length: int
    max_summary_count: int
    gap_to_trigger_ratio: float
    quiet_runs_before_compression: QuietRunsSettings
    outbox_health_threshold: int

    @classmethod
    def from_dict(cls, block: dict) -> "ChatCompressionSettings":
        required_keys = (
            "size_trigger_threshold",
            "min_chunk_length",
            "max_summary_count",
            "gap_to_trigger_ratio",
            "quiet_runs_before_compression",
            "outbox_health_threshold",
        )
        for key in required_keys:
            if key not in block:
                raise ValueError(f"Missing required key: {key}")

        quiet_block = block["quiet_runs_before_compression"]
        for key in ("private", "group"):
            if key not in quiet_block:
                raise ValueError(f"Missing required key: quiet_runs_before_compression.{key}")

        return cls(
            size_trigger_threshold=int(block["size_trigger_threshold"]),
            min_chunk_length=int(block["min_chunk_length"]),
            max_summary_count=int(block["max_summary_count"]),
            gap_to_trigger_ratio=float(block["gap_to_trigger_ratio"]),
            quiet_runs_before_compression=QuietRunsSettings(
                private=int(quiet_block["private"]),
                group=int(quiet_block["group"]),
            ),
            outbox_health_threshold=int(block["outbox_health_threshold"]),
        )
