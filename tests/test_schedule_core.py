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


@pytest.mark.parametrize(
    "timezone",
    ["Europe/Moscow", "UTC", "America/New_York"],
)
def test_validate_timezone_name_valid_iana(timezone: str) -> None:
    assert ScheduleCore.validate_timezone_name(timezone) is None


@pytest.mark.parametrize(
    "timezone",
    [None, "", "   ", "Invalid/Zone", "+03:00", "UTC+03:00"],
)
def test_validate_timezone_name_rejects_missing_invalid_offset(
    timezone: str | None,
) -> None:
    err = ScheduleCore.validate_timezone_name(timezone)
    assert isinstance(err, str)
    assert err


def test_relative_timezone_name_picks_explicit() -> None:
    assert (
        ScheduleCore.relative_timezone_name("Europe/Berlin", "America/New_York")
        == "Europe/Berlin"
    )


def test_relative_timezone_name_falls_back_to_valid_profile() -> None:
    assert (
        ScheduleCore.relative_timezone_name(None, "Europe/Moscow") == "Europe/Moscow"
    )
    assert ScheduleCore.relative_timezone_name("", "Europe/Moscow") == "Europe/Moscow"


def test_relative_timezone_name_defaults_to_utc() -> None:
    assert ScheduleCore.relative_timezone_name(None, None) == "UTC"
    assert ScheduleCore.relative_timezone_name(None, "Invalid/Zone") == "UTC"
    assert ScheduleCore.relative_timezone_name("+03:00", None) == "UTC"


def test_relative_timezone_name_invalid_profile_does_not_poison_explicit() -> None:
    assert (
        ScheduleCore.relative_timezone_name("Europe/Moscow", "Invalid/Zone")
        == "Europe/Moscow"
    )


def test_resolve_absolute_dst_spring_transition_berlin() -> None:
    """Europe/Berlin spring 2026: clocks jump 02:00 → 03:00 on 29 Mar.

    Unambiguous local wall times on either side of the gap.
    """
    before = ScheduleCore.resolve_absolute(
        year=2026,
        month=3,
        day=29,
        hour=1,
        minute=30,
        timezone="Europe/Berlin",
    )
    after = ScheduleCore.resolve_absolute(
        year=2026,
        month=3,
        day=29,
        hour=3,
        minute=30,
        timezone="Europe/Berlin",
    )
    assert isinstance(before, ResolvedOnce)
    assert isinstance(after, ResolvedOnce)
    assert before.utc_dt.hour == 0 and before.utc_dt.minute == 30
    assert before.utc_dt.utcoffset() is not None
    assert before.utc_dt.astimezone(ZoneInfo("Europe/Berlin")).utcoffset().total_seconds() == 3600
    assert after.utc_dt.hour == 1 and after.utc_dt.minute == 30
    assert after.utc_dt.astimezone(ZoneInfo("Europe/Berlin")).utcoffset().total_seconds() == 7200


def test_resolve_absolute_dst_autumn_transition_berlin() -> None:
    """Europe/Berlin autumn 2026: clocks fall back 03:00 → 02:00 on 25 Oct.

    Unambiguous local wall times outside the duplicated hour.
    """
    before = ScheduleCore.resolve_absolute(
        year=2026,
        month=10,
        day=25,
        hour=1,
        minute=30,
        timezone="Europe/Berlin",
    )
    after = ScheduleCore.resolve_absolute(
        year=2026,
        month=10,
        day=25,
        hour=3,
        minute=30,
        timezone="Europe/Berlin",
    )
    assert isinstance(before, ResolvedOnce)
    assert isinstance(after, ResolvedOnce)
    assert before.utc_dt.astimezone(ZoneInfo("Europe/Berlin")).utcoffset().total_seconds() == 7200
    assert after.utc_dt.astimezone(ZoneInfo("Europe/Berlin")).utcoffset().total_seconds() == 3600
    assert before.utc_dt.hour == 23 and before.utc_dt.day == 24
    assert after.utc_dt.hour == 2 and after.utc_dt.minute == 30


def test_parse_cron_dst_keeps_local_wall_time_through_transitions() -> None:
    """Daily 09:00 Europe/Berlin stays at local 09:00 across spring and autumn."""
    trigger = ScheduleCore.parse_cron("0 9 * * *", "Europe/Berlin")
    assert not isinstance(trigger, str)
    berlin = ZoneInfo("Europe/Berlin")
    # Start just before spring transition week
    now = datetime(2026, 3, 27, 0, 0, tzinfo=berlin)
    previous: datetime | None = None
    fire_times: list[datetime] = []
    for _ in range(250):
        nxt = trigger.get_next_fire_time(previous, now)
        assert nxt is not None
        fire_times.append(nxt)
        previous = nxt
        now = nxt
        if nxt.date() > datetime(2026, 11, 1).date():
            break

    spring_side = [ft for ft in fire_times if ft.date() in (
        datetime(2026, 3, 28).date(),
        datetime(2026, 3, 29).date(),
        datetime(2026, 3, 30).date(),
    )]
    autumn_side = [ft for ft in fire_times if ft.date() in (
        datetime(2026, 10, 24).date(),
        datetime(2026, 10, 25).date(),
        datetime(2026, 10, 26).date(),
    )]
    assert spring_side
    assert autumn_side
    for ft in spring_side + autumn_side:
        local = ft.astimezone(berlin)
        assert local.hour == 9
        assert local.minute == 0
    # Offset must change across the spring and autumn transitions
    offsets_spring = {
        ft.astimezone(berlin).utcoffset().total_seconds() for ft in spring_side
    }
    offsets_autumn = {
        ft.astimezone(berlin).utcoffset().total_seconds() for ft in autumn_side
    }
    assert 3600 in offsets_spring and 7200 in offsets_spring
    assert 3600 in offsets_autumn and 7200 in offsets_autumn
