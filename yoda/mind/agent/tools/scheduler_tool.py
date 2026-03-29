import json
import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.agent.data.agent_data import ToolCall, ToolResult
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)

ACTIVE_JOBS_KEY_PREFIX = "active_jobs"


class ScheduleMessageParams(BaseModel):
    reminder_text: str
    delay_minutes: int | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    minute: int | None = None
    timezone: str | None = None


class SchedulerTool(Tool):
    name = "schedule_message"
    parameters_schema = ScheduleMessageParams
    terminal = True

    def __init__(self, scheduler_api: SchedulerApi, storage_api: StorageApi):
        self._scheduler_api = scheduler_api
        self._storage_api = storage_api

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = ScheduleMessageParams(**call.arguments)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                output=f"Invalid parameters: {e}",
                success=False,
            )

        chat_id = call.metadata.get("chat_id")
        if chat_id is None:
            return ToolResult(
                tool_name=self.name,
                output="Missing chat_id in metadata",
                success=False,
            )

        tz_for_meta = self._effective_timezone_name(params, call)

        if params.delay_minutes is not None:
            utc_dt, display_str = self._resolve_relative(params, tz_for_meta)
        elif params.year is not None and params.timezone is not None:
            result = self._resolve_absolute(params)
            if isinstance(result, ToolResult):
                return result
            utc_dt, display_str = result
            tz_for_meta = params.timezone
        else:
            return ToolResult(
                tool_name=self.name,
                output="Provide either delay_minutes OR (year/month/day/hour/minute + timezone)",
                success=False,
            )

        if utc_dt <= datetime.now(ZoneInfo("UTC")):
            return ToolResult(
                tool_name=self.name,
                output="Cannot schedule a reminder in the past",
                success=False,
            )

        job_id = f"reminder_{chat_id}_{uuid.uuid4().hex[:8]}"

        self._scheduler_api.schedule_once(
            job_id=job_id,
            run_date=utc_dt,
            chat_id=chat_id,
            text=params.reminder_text,
        )

        await self._save_job_metadata(
            chat_id=chat_id,
            job_id=job_id,
            job_type="once",
            description=params.reminder_text,
            deliver_at_utc=utc_dt.isoformat(),
            timezone=tz_for_meta,
        )

        return ToolResult(
            tool_name=self.name,
            output=f"Reminder scheduled: '{params.reminder_text}' — {display_str}",
            success=True,
        )

    @staticmethod
    def _effective_timezone_name(
        params: ScheduleMessageParams, call: ToolCall
    ) -> str:
        raw = (
            params.timezone
            or (call.metadata.get("profile_timezone") or "").strip()
            or None
        )
        if raw is None:
            return "UTC"
        try:
            ZoneInfo(raw)
            return raw
        except (KeyError, ValueError):
            return "UTC"

    @staticmethod
    def _resolve_relative(
        params: ScheduleMessageParams, tz_name: str
    ) -> tuple[datetime, str]:
        utc_dt = datetime.now(ZoneInfo("UTC")) + timedelta(
            minutes=params.delay_minutes
        )
        try:
            local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
            local_part = f" at {local_dt.strftime('%Y-%m-%d %H:%M')}"
        except (KeyError, ValueError):
            local_part = ""
        return utc_dt, f"in {params.delay_minutes} minutes{local_part}"

    @staticmethod
    def _resolve_absolute(params: ScheduleMessageParams) -> tuple[datetime, str] | ToolResult:
        try:
            tz = ZoneInfo(params.timezone)
        except (KeyError, ValueError):
            return ToolResult(
                tool_name="schedule_message",
                output=f"Unknown timezone: {params.timezone}",
                success=False,
            )
        try:
            local_dt = datetime(
                year=params.year,
                month=params.month,
                day=params.day,
                hour=params.hour,
                minute=params.minute,
                tzinfo=tz,
            )
        except (ValueError, TypeError) as e:
            return ToolResult(
                tool_name="schedule_message",
                output=f"Invalid date/time: {e}",
                success=False,
            )
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
        display_str = f"at {local_dt.strftime('%Y-%m-%d %H:%M')} ({params.timezone})"
        return utc_dt, display_str

    async def _save_job_metadata(
        self,
        chat_id: int,
        job_id: str,
        job_type: str,
        description: str,
        deliver_at_utc: str,
        timezone: str,
    ) -> None:
        metadata = json.dumps({
            "job_id": job_id,
            "type": job_type,
            "description": description,
            "deliver_at_utc": deliver_at_utc,
            "timezone": timezone,
        })
        key = f"{ACTIVE_JOBS_KEY_PREFIX}:{chat_id}"
        await self._storage_api.hset(key, job_id, metadata)
