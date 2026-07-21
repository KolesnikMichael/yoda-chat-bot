import json
import logging
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.agent.core.schedule_core import ScheduleCore
from yoda.mind.agent.data.agent_data import RequestConstraints, ToolCall, ToolResult
from yoda.mind.agent.data.outcome_data import JobKind, ResultKind, TerminalResultFacts
from yoda.mind.agent.tools.job_keys import active_jobs_key
from yoda.mind.agent.tools.tool_port import Tool

logger = logging.getLogger(__name__)


class ScheduleTaskParams(BaseModel):
    skill_name: str
    distilled_task: str
    description: str
    delay_minutes: int | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    minute: int | None = None
    timezone: str | None = None
    cron: str | None = None
    request_constraints: RequestConstraints = Field(
        default_factory=RequestConstraints,
    )


class ScheduleTaskTool(Tool):
    name = "schedule_task"
    parameters_schema = ScheduleTaskParams
    terminal = True

    def __init__(
        self,
        scheduler_api: SchedulerApi,
        storage_api: StorageApi,
        skills_dir: Path,
    ):
        self._scheduler_api = scheduler_api
        self._storage_api = storage_api
        self._skills_dir = skills_dir

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            params = ScheduleTaskParams(**call.arguments)
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
        user_id = call.metadata.get("user_id", 0)

        task_err = ScheduleCore.validate_distilled_task(params.distilled_task)
        if task_err:
            return ToolResult(tool_name=self.name, output=task_err, success=False)

        skill_or_err = ScheduleCore.load_skill(
            self._skills_dir, params.skill_name
        )
        if isinstance(skill_or_err, str):
            return ToolResult(
                tool_name=self.name,
                output=skill_or_err,
                success=False,
            )

        absolute_fields = (
            params.year,
            params.month,
            params.day,
            params.hour,
            params.minute,
        )
        has_any_absolute = any(value is not None for value in absolute_fields)
        has_absolute = all(value is not None for value in absolute_fields)
        if has_any_absolute and not has_absolute:
            return ToolResult(
                tool_name=self.name,
                output=(
                    "Absolute time requires all of: "
                    "year/month/day/hour/minute + timezone"
                ),
                success=False,
            )
        mode_count = ScheduleCore.count_timing_modes(
            cron=params.cron,
            delay_minutes=params.delay_minutes,
            has_absolute=has_absolute,
        )
        if mode_count != 1:
            return ToolResult(
                tool_name=self.name,
                output=(
                    "Provide exactly one of: cron, delay_minutes, "
                    "or (year/month/day/hour/minute + timezone)"
                ),
                success=False,
            )

        is_cron = params.cron is not None and str(params.cron).strip()
        if is_cron or has_absolute:
            tz_err = ScheduleCore.validate_timezone_name(params.timezone)
            if tz_err:
                return ToolResult(
                    tool_name=self.name,
                    output=tz_err,
                    success=False,
                )
            tz_for_meta = str(params.timezone).strip()
        else:
            tz_for_meta = ScheduleCore.relative_timezone_name(
                params.timezone,
                call.metadata.get("profile_timezone"),
            )

        job_id = f"task_{chat_id}_{uuid.uuid4().hex[:8]}"

        if is_cron:
            cron_expr = params.cron.strip()
            if ScheduleCore.cron_interval_too_frequent(cron_expr, tz_for_meta):
                return ToolResult(
                    tool_name=self.name,
                    output=(
                        f"Recurring schedule must be at least "
                        f"{ScheduleCore.MIN_CRON_INTERVAL_MINUTES} minutes apart"
                    ),
                    success=False,
                )
            parsed = ScheduleCore.parse_cron(cron_expr, tz_for_meta)
            if isinstance(parsed, str):
                return ToolResult(
                    tool_name=self.name,
                    output=parsed,
                    success=False,
                )
            self._scheduler_api.schedule_cron(
                job_id=job_id,
                cron_expr=cron_expr,
                timezone=tz_for_meta,
                chat_id=chat_id,
            )
            display_str = ScheduleCore.describe_cron(cron_expr, tz_for_meta)
            await self._save_job_metadata(
                chat_id=chat_id,
                job_id=job_id,
                schedule_type="cron",
                description=params.description,
                deliver_at_utc=None,
                cron=cron_expr,
                timezone=tz_for_meta,
                user_id=user_id,
                skill_name=params.skill_name,
                distilled_task=params.distilled_task,
                request_constraints=params.request_constraints,
            )
        else:
            if params.delay_minutes is not None:
                resolved = ScheduleCore.resolve_relative(
                    params.delay_minutes, tz_for_meta
                )
            else:
                assert has_absolute
                result = ScheduleCore.resolve_absolute(
                    year=params.year,
                    month=params.month,
                    day=params.day,
                    hour=params.hour,
                    minute=params.minute,
                    timezone=tz_for_meta,
                )
                if isinstance(result, str):
                    return ToolResult(
                        tool_name=self.name,
                        output=result,
                        success=False,
                    )
                resolved = result

            if ScheduleCore.is_in_past(resolved.utc_dt):
                return ToolResult(
                    tool_name=self.name,
                    output="Cannot schedule a task in the past",
                    success=False,
                )

            self._scheduler_api.schedule_once(
                job_id=job_id,
                run_date=resolved.utc_dt,
                chat_id=chat_id,
            )
            display_str = resolved.display_str
            await self._save_job_metadata(
                chat_id=chat_id,
                job_id=job_id,
                schedule_type="once",
                description=params.description,
                deliver_at_utc=resolved.utc_dt.isoformat(),
                cron=None,
                timezone=tz_for_meta,
                user_id=user_id,
                skill_name=params.skill_name,
                distilled_task=params.distilled_task,
                request_constraints=params.request_constraints,
            )

        return ToolResult(
            tool_name=self.name,
            output=(
                f"Task scheduled ({params.skill_name}): "
                f"'{params.description}' — {display_str}"
            ),
            success=True,
            terminal_facts=TerminalResultFacts(
                result_kind=ResultKind.SCHEDULED_JOB,
                summary=f"Scheduled task set for {display_str}.",
                job_kind=JobKind.TASK,
                scheduled_skill_name=params.skill_name,
                schedule=display_str,
            ),
        )

    async def _save_job_metadata(
        self,
        *,
        chat_id: int,
        job_id: str,
        schedule_type: str,
        description: str,
        deliver_at_utc: str | None,
        cron: str | None,
        timezone: str,
        user_id: int,
        skill_name: str,
        distilled_task: str,
        request_constraints: RequestConstraints,
    ) -> None:
        metadata = json.dumps({
            "job_id": job_id,
            "type": schedule_type,
            "kind": "task",
            "description": description,
            "deliver_at_utc": deliver_at_utc,
            "cron": cron,
            "timezone": timezone,
            "user_id": user_id,
            "skill_name": skill_name,
            "distilled_task": distilled_task,
            "request_constraints": request_constraints.model_dump(),
        })
        await self._storage_api.hset(active_jobs_key(chat_id), job_id, metadata)
