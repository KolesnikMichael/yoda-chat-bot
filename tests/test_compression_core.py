import datetime as dtm
import json
from pathlib import Path

import pytest

from yoda.mind.memory.compression_core import CompressionCore
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.memory import MemoryCore, VISIBLE_KINDS


def default_compression_settings() -> ChatCompressionSettings:
    settings_path = Path(__file__).resolve().parents[1] / "settings.json"
    block = json.loads(settings_path.read_text())["mind"]["memory"]["chat_compression"]
    return ChatCompressionSettings.from_dict(block)


def _msg(
    kind: str,
    *,
    timestamp: str = "",
    role: str = "system",
    user_id: int | None = None,
) -> Message:
    return Message(
        role=role,
        kind=kind,  # type: ignore[arg-type]
        timestamp=timestamp,
        user_id=user_id,
    )


# --- Stage 1: visibility, timestamp, gap threshold ---


def test_is_visible_true_for_user_and_assistant():
    assert CompressionCore.is_visible(_msg("user", user_id=1)) is True
    assert CompressionCore.is_visible(_msg("assistant", role="assistant")) is True


def test_is_visible_false_for_non_visible_kinds():
    for kind in ("prompt", "summary", "task_result", "user_introduction"):
        assert CompressionCore.is_visible(_msg(kind)) is False


def test_visible_kinds_parity_with_memory():
    from yoda.mind.memory import compression_core as compression_core_module

    assert compression_core_module._VISIBLE_KINDS == VISIBLE_KINDS


def test_parse_message_timestamp():
    assert CompressionCore.parse_message_timestamp("") == 0.0
    iso_ts = CompressionCore.parse_message_timestamp("2026-03-09T21:36:51+00:00")
    space_ts = CompressionCore.parse_message_timestamp("2026-03-09 21:36:51+00:00")
    assert iso_ts == space_ts
    assert iso_ts > 0.0
    assert iso_ts == MemoryCore.parse_message_timestamp("2026-03-09T21:36:51+00:00")
    assert CompressionCore.parse_message_timestamp("not-a-date") == 0.0


def test_gap_threshold_defaults_private_and_group():
    settings = default_compression_settings()
    assert CompressionCore.gap_threshold_seconds(settings, "private", 3600.0) == 14400.0
    assert CompressionCore.gap_threshold_seconds(settings, "group", 3600.0) == 14400.0


def test_gap_threshold_group_quiet_runs_independent():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 30,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 12},
        "outbox_health_threshold": 10,
    })
    assert CompressionCore.gap_threshold_seconds(settings, "private", 3600.0) == 14400.0
    assert CompressionCore.gap_threshold_seconds(settings, "group", 3600.0) == 21600.0


def test_gap_threshold_invalid_chat_type_raises():
    settings = default_compression_settings()
    with pytest.raises(ValueError, match="Unknown chat_type"):
        CompressionCore.gap_threshold_seconds(settings, "channel", 3600.0)


# --- Stage 2: boundary alignment ---


def test_align_boundary_noop_when_candidate_is_user():
    messages = [
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
    ]
    assert CompressionCore.align_boundary(messages, 0) == 0


def test_align_boundary_shifts_assistant_forward_to_next_user():
    messages = [
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=2),
    ]
    assert CompressionCore.align_boundary(messages, 1) == 2


def test_align_boundary_returns_len_when_no_forward_user():
    messages = [
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
    ]
    assert CompressionCore.align_boundary(messages, 1) == 2


def test_align_boundary_group_tail_with_introduction_still_aligns_on_user():
    messages = [
        _msg("user", user_id=1),
        _msg("user_introduction"),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=2),
    ]
    assert CompressionCore.align_boundary(messages, 2) == 3


# --- Stage 3: size-trigger window ---


def test_select_size_trigger_window_even_visible_with_interleaved_non_visible():
    messages = [
        _msg("prompt"),
        _msg("user", user_id=1),
        _msg("summary"),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=1),
        _msg("task_result"),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=2),
    ]
    # 4 visible: indices 1,3,4,6,7 -> k=2, (k+1)-th visible at index 4 (user)
    split = CompressionCore.select_size_trigger_window(messages)
    assert split == 4
    assert messages[split].kind == "user"


def test_select_size_trigger_window_odd_visible_count():
    messages = [
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=2),
    ]
    # 5 visible -> k=2, split at 3rd visible (index 2, user)
    split = CompressionCore.select_size_trigger_window(messages)
    assert split == 2
    assert messages[split].kind == "user"


def test_select_size_trigger_window_halve_on_assistant_aligns_forward():
    messages = [
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
    ]
    # 4 visible -> k=2, candidate index 2 (user) — already user
    split = CompressionCore.select_size_trigger_window(messages)
    assert split == 2


def test_select_size_trigger_window_returns_none_for_zero_width():
    messages = [_msg("user", user_id=1)]
    assert CompressionCore.select_size_trigger_window(messages) is None


def test_select_size_trigger_window_returns_none_when_alignment_exhausts():
    messages = [
        _msg("user", user_id=1),
        _msg("assistant", role="assistant"),
    ]
    # 2 visible -> k=1, candidate index 1 (assistant), align -> 2 == len -> None
    assert CompressionCore.select_size_trigger_window(messages) is None


# --- Stage 4: timeout-trigger window ---


def _ts(hours: float) -> str:
    base = dtm.datetime(2026, 3, 9, 12, 0, 0, tzinfo=dtm.timezone.utc)
    return (base + dtm.timedelta(hours=hours)).isoformat()


def test_timeout_trigger_window_finds_gap_and_retains_min_chunk():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 3,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })
    # Visible at 0h, 1h, 2h, 8h, 9h, 10h — 5h gap between index 2 and 3
    messages = [
        _msg("user", user_id=1, timestamp=_ts(0)),
        _msg("assistant", role="assistant", timestamp=_ts(1)),
        _msg("user", user_id=1, timestamp=_ts(2)),
        _msg("user", user_id=1, timestamp=_ts(8)),
        _msg("assistant", role="assistant", timestamp=_ts(9)),
        _msg("user", user_id=2, timestamp=_ts(10)),
    ]
    split = CompressionCore.select_timeout_trigger_window(
        messages, settings, "private", 3600.0
    )
    assert split is not None
    assert split == 3
    tail_visible = sum(
        1 for m in messages[split:] if CompressionCore.is_visible(m)
    )
    assert tail_visible >= settings.min_chunk_length


def test_timeout_trigger_window_no_gap_returns_none():
    settings = default_compression_settings()
    settings = ChatCompressionSettings.from_dict({
        **{
            "size_trigger_threshold": settings.size_trigger_threshold,
            "min_chunk_length": 3,
            "max_summary_count": settings.max_summary_count,
            "gap_to_trigger_ratio": settings.gap_to_trigger_ratio,
            "quiet_runs_before_compression": {
                "private": settings.quiet_runs_before_compression.private,
                "group": settings.quiet_runs_before_compression.group,
            },
            "outbox_health_threshold": settings.outbox_health_threshold,
        }
    })
    messages = [
        _msg("user", user_id=1, timestamp=_ts(0)),
        _msg("assistant", role="assistant", timestamp=_ts(1)),
        _msg("user", user_id=1, timestamp=_ts(2)),
        _msg("assistant", role="assistant", timestamp=_ts(3)),
        _msg("user", user_id=2, timestamp=_ts(4)),
    ]
    assert CompressionCore.select_timeout_trigger_window(
        messages, settings, "private", 3600.0
    ) is None


def test_timeout_trigger_window_task_result_sandwich_does_not_split_burst():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 2,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })
    messages = [
        _msg("user", user_id=1, timestamp=_ts(0)),
        _msg("assistant", role="assistant", timestamp=_ts(1)),
        _msg("user", user_id=1, timestamp=_ts(10)),
        _msg("task_result", timestamp=_ts(10.5)),
        _msg("assistant", role="assistant", timestamp=_ts(11)),
        _msg("user", user_id=2, timestamp=_ts(12)),
    ]
    split = CompressionCore.select_timeout_trigger_window(
        messages, settings, "private", 3600.0
    )
    assert split is not None
    assert split == 2


def test_timeout_trigger_window_non_visible_inside_gap_goes_to_live_tail():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 2,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })
    messages = [
        _msg("user", user_id=1, timestamp=_ts(0)),
        _msg("summary", timestamp=_ts(0.5)),
        _msg("user", user_id=1, timestamp=_ts(10)),
        _msg("assistant", role="assistant", timestamp=_ts(11)),
        _msg("user", user_id=2, timestamp=_ts(12)),
    ]
    split = CompressionCore.select_timeout_trigger_window(
        messages, settings, "private", 3600.0
    )
    assert split == 2
    assert messages[0].kind == "user"
    assert messages[0] in messages[:split]


def test_timeout_trigger_window_no_size_fallback():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 2,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })
    messages = [
        _msg("user", user_id=1, timestamp=_ts(0)),
        _msg("assistant", role="assistant", timestamp=_ts(1)),
        _msg("user", user_id=1, timestamp=_ts(2)),
        _msg("assistant", role="assistant", timestamp=_ts(3)),
        _msg("user", user_id=2, timestamp=_ts(4)),
    ]
    timeout_split = CompressionCore.select_timeout_trigger_window(
        messages, settings, "private", 3600.0
    )
    size_split = CompressionCore.select_size_trigger_window(messages)
    assert timeout_split is None
    assert size_split is not None


def test_timeout_trigger_window_multiple_gaps_picks_nearest_to_tail():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 1,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 8},
        "outbox_health_threshold": 10,
    })
    messages = [
        _msg("user", user_id=1, timestamp=_ts(0)),
        _msg("user", user_id=1, timestamp=_ts(20)),
        _msg("user", user_id=1, timestamp=_ts(22)),
        _msg("user", user_id=2, timestamp=_ts(30)),
    ]
    split = CompressionCore.select_timeout_trigger_window(
        messages, settings, "private", 3600.0
    )
    assert split == 3


# --- Stage 5: firing predicates ---


def test_should_fire_size_trigger_boundary():
    settings = default_compression_settings()
    assert CompressionCore.should_fire_size_trigger(300, settings) is False
    assert CompressionCore.should_fire_size_trigger(301, settings) is True


def test_passes_timeout_entry_guard_boundary():
    settings = default_compression_settings()
    assert CompressionCore.passes_timeout_entry_guard(60, settings) is False
    assert CompressionCore.passes_timeout_entry_guard(61, settings) is True


def test_is_quiet_for_n_runs_boundary():
    settings = default_compression_settings()
    last_visible_at = 1000.0
    quiet_seconds = 8 * 3600.0
    assert CompressionCore.is_quiet_for_n_runs(
        last_visible_at, last_visible_at + quiet_seconds - 1, settings, "private", 3600.0
    ) is False
    assert CompressionCore.is_quiet_for_n_runs(
        last_visible_at, last_visible_at + quiet_seconds, settings, "private", 3600.0
    ) is True


def test_is_quiet_for_n_runs_invalid_chat_type_raises():
    settings = default_compression_settings()
    with pytest.raises(ValueError, match="Unknown chat_type"):
        CompressionCore.is_quiet_for_n_runs(0.0, 100.0, settings, "unknown", 3600.0)


def test_has_visible_activity_since_compression():
    assert CompressionCore.has_visible_activity_since_compression(1.0, 0.0) is True
    assert CompressionCore.has_visible_activity_since_compression(1.0, 1.0) is False
    assert CompressionCore.has_visible_activity_since_compression(1.0, 2.0) is False


def test_should_evaluate_timeout_trigger_composite():
    settings = default_compression_settings()
    quiet_seconds = 8 * 3600.0
    last_visible_at = 100.0
    now = last_visible_at + quiet_seconds

    assert CompressionCore.should_evaluate_timeout_trigger(
        61, last_visible_at, 0.0, now, settings, "private", 3600.0
    ) is True

    assert CompressionCore.should_evaluate_timeout_trigger(
        60, last_visible_at, 0.0, now, settings, "private", 3600.0
    ) is False

    assert CompressionCore.should_evaluate_timeout_trigger(
        61, last_visible_at, last_visible_at + 1, now, settings, "private", 3600.0
    ) is False

    assert CompressionCore.should_evaluate_timeout_trigger(
        61, last_visible_at, 0.0, last_visible_at + quiet_seconds - 1,
        settings, "private", 3600.0
    ) is False


# --- Stage 6: import hygiene ---


def test_compression_core_static_methods_only():
    for name, attr in CompressionCore.__dict__.items():
        if name.startswith("__"):
            continue
        if callable(attr):
            assert isinstance(attr, staticmethod), name


def test_compression_core_imports_only_data_types():
    import ast
    from pathlib import Path

    source = Path("yoda/mind/memory/compression_core.py").read_text()
    tree = ast.parse(source)
    imports = {
        node.names[0].name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports_from = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }
    forbidden_modules = (
        "yoda.mind.mind",
        "yoda.mind.memory.memory",
        "yoda.api",
    )
    for module in imports:
        assert not any(module.startswith(f) for f in forbidden_modules)
    for module, _ in imports_from:
        assert (
            module.startswith("yoda.mind.memory.data")
            or module.startswith("data.")
            or module in ("datetime", "typing")
        )
