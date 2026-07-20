from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from yoda.mind.agent.data.agent_data import SkillSpec
from yoda.mind.agent.skills.catalog import SkillCatalog

FORBIDDEN_SCHEDULE_SKILL_NAMES = frozenset({"schedule_message", "schedule_task"})
MIN_CRON_INTERVAL_MINUTES = 5


@dataclass(frozen=True)
class ResolvedOnce:
    utc_dt: datetime
    display_str: str
    timezone: str


class ScheduleCore:
    MIN_CRON_INTERVAL_MINUTES = MIN_CRON_INTERVAL_MINUTES

    @staticmethod
    def validate_timezone_name(timezone: str | None) -> str | None:
        if timezone is None or not str(timezone).strip():
            return "timezone is required and must be a valid IANA name"
        raw = str(timezone).strip()
        try:
            ZoneInfo(raw)
        except (KeyError, ValueError):
            return f"Unknown timezone: {raw}"
        return None

    @staticmethod
    def relative_timezone_name(
        explicit_tz: str | None,
        profile_timezone: str | None,
    ) -> str:
        for candidate in (explicit_tz, profile_timezone):
            if candidate is None or not str(candidate).strip():
                continue
            raw = str(candidate).strip()
            try:
                ZoneInfo(raw)
                return raw
            except (KeyError, ValueError):
                continue
        return "UTC"

    @staticmethod
    def count_timing_modes(
        *,
        cron: str | None,
        delay_minutes: int | None,
        has_absolute: bool,
    ) -> int:
        modes = 0
        if cron is not None and str(cron).strip():
            modes += 1
        if delay_minutes is not None:
            modes += 1
        if has_absolute:
            modes += 1
        return modes

    @staticmethod
    def resolve_relative(
        delay_minutes: int,
        tz_name: str,
    ) -> ResolvedOnce:
        utc_dt = datetime.now(ZoneInfo("UTC")) + timedelta(minutes=delay_minutes)
        try:
            local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
            local_part = f" at {local_dt.strftime('%Y-%m-%d %H:%M')}"
        except (KeyError, ValueError):
            local_part = ""
        display = f"in {delay_minutes} minutes{local_part}"
        return ResolvedOnce(utc_dt=utc_dt, display_str=display, timezone=tz_name)

    @staticmethod
    def resolve_absolute(
        *,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        timezone: str,
    ) -> ResolvedOnce | str:
        try:
            tz = ZoneInfo(timezone)
        except (KeyError, ValueError):
            return f"Unknown timezone: {timezone}"
        try:
            local_dt = datetime(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                tzinfo=tz,
            )
        except (ValueError, TypeError) as e:
            return f"Invalid date/time: {e}"
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        display = f"at {local_dt.strftime('%Y-%m-%d %H:%M')} ({timezone})"
        return ResolvedOnce(utc_dt=utc_dt, display_str=display, timezone=timezone)

    @staticmethod
    def is_in_past(utc_dt: datetime) -> bool:
        return utc_dt <= datetime.now(ZoneInfo("UTC"))

    @staticmethod
    def parse_cron(cron_expr: str, timezone: str) -> CronTrigger | str:
        try:
            tz = ZoneInfo(timezone)
        except (KeyError, ValueError):
            return f"Unknown timezone: {timezone}"
        try:
            return CronTrigger.from_crontab(cron_expr.strip(), timezone=tz)
        except ValueError as e:
            return f"Invalid cron expression: {e}"

    @staticmethod
    def describe_cron(cron_expr: str, timezone: str) -> str:
        return f"cron '{cron_expr.strip()}' ({timezone})"

    @staticmethod
    def cron_interval_too_frequent(cron_expr: str, timezone: str) -> bool:
        """True if cron would fire more often than MIN_CRON_INTERVAL_MINUTES."""
        _ = timezone  # reserved for future timezone-aware checks
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False
        minute_field, hour_field = parts[0], parts[1]
        if minute_field == "*":
            return True
        if minute_field.startswith("*/"):
            try:
                step = int(minute_field[2:])
                return step < MIN_CRON_INTERVAL_MINUTES
            except ValueError:
                return False
        if minute_field == "*" and hour_field == "*":
            return True
        return False

    @staticmethod
    def load_skill(skills_dir: Path, skill_name: str) -> SkillSpec | str:
        if skill_name in FORBIDDEN_SCHEDULE_SKILL_NAMES:
            return f"Cannot schedule skill '{skill_name}'"
        try:
            return SkillCatalog.load_skill(skills_dir, skill_name)
        except ValueError:
            return f"Unknown skill: {skill_name}"

    @staticmethod
    def validate_distilled_task(distilled_task: str) -> str | None:
        if not distilled_task or not distilled_task.strip():
            return "distilled_task must be a non-empty self-contained task description"
        return None
