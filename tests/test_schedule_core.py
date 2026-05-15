from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from yoda.mind.agent.core.schedule_core import ResolvedOnce, ScheduleCore


def test_resolve_relative():
    resolved = ScheduleCore.resolve_relative(30, "UTC")
    assert resolved.display_str.startswith("in 30 minutes")
    assert resolved.utc_dt > datetime.now(ZoneInfo("UTC"))


def test_resolve_absolute():
    result = ScheduleCore.resolve_absolute(
        year=2030,
        month=6,
        day=15,
        hour=14,
        minute=30,
        timezone="Europe/Moscow",
    )
    assert isinstance(result, ResolvedOnce)
    assert "2030" in result.display_str


def test_resolve_absolute_unknown_timezone():
    err = ScheduleCore.resolve_absolute(
        year=2030,
        month=1,
        day=1,
        hour=12,
        minute=0,
        timezone="Invalid/Zone",
    )
    assert isinstance(err, str)
    assert "timezone" in err.lower()


def test_parse_cron_valid():
    trigger = ScheduleCore.parse_cron("0 9 * * *", "UTC")
    assert not isinstance(trigger, str)


def test_parse_cron_invalid():
    err = ScheduleCore.parse_cron("not a cron", "UTC")
    assert isinstance(err, str)


def test_cron_interval_too_frequent():
    assert ScheduleCore.cron_interval_too_frequent("* * * * *", "UTC") is True


def test_cron_interval_daily_ok():
    assert ScheduleCore.cron_interval_too_frequent("0 9 * * *", "UTC") is False


def test_validate_distilled_task_empty():
    assert ScheduleCore.validate_distilled_task("  ") is not None


def test_count_timing_modes():
    assert ScheduleCore.count_timing_modes(
        cron=None, delay_minutes=5, has_absolute=False
    ) == 1
    assert ScheduleCore.count_timing_modes(
        cron="0 9 * * *", delay_minutes=5, has_absolute=False
    ) == 2
