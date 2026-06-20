from dataclasses import dataclass

from .conversation import Conversation


@dataclass
class CompressionSnapshot:
    n_old: int
    copy: Conversation
    snapshot_ts: float


@dataclass
class CompressionTransformResult:
    copy: Conversation
    removed_users: set[int]
    audit_entry: dict
    chunk_visible_count: int
