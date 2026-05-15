import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_fire_callback: Callable[..., Coroutine[Any, Any, None]] | None = None
_cleanup_callback: Callable[..., Coroutine[Any, Any, None]] | None = None


async def _fire_job(chat_id: int, job_id: str, schedule_type: str) -> None:
    if _fire_callback is None:
        logger.error("Fire callback not set, cannot deliver scheduled job")
        return
    await _fire_callback(chat_id, job_id)
    if _cleanup_callback and schedule_type == "once":
        await _cleanup_callback(chat_id, job_id)


class SchedulerApi:
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        jobstore = RedisJobStore(host=redis_host, port=redis_port, db=redis_db)
        self._scheduler = AsyncIOScheduler(jobstores={"default": jobstore})

    def set_fire_callback(
        self, callback: Callable[..., Coroutine[Any, Any, None]]
    ) -> None:
        global _fire_callback
        _fire_callback = callback

    def set_cleanup_callback(
        self, callback: Callable[..., Coroutine[Any, Any, None]]
    ) -> None:
        global _cleanup_callback
        _cleanup_callback = callback

    def start(self) -> None:
        self._scheduler.start()
        logger.debug("Scheduler started")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.debug("Scheduler shut down")

    def schedule_once(
        self,
        job_id: str,
        run_date: datetime,
        chat_id: int,
    ) -> None:
        self._scheduler.add_job(
            func=_fire_job,
            trigger="date",
            run_date=run_date,
            args=[chat_id, job_id, "once"],
            id=job_id,
            replace_existing=True,
        )
        logger.info(
            f"Scheduled one-time job {job_id} at {run_date} in chat {chat_id}"
        )

    def schedule_cron(
        self,
        job_id: str,
        cron_expr: str,
        timezone: str,
        chat_id: int,
    ) -> None:
        tz = ZoneInfo(timezone)
        trigger = CronTrigger.from_crontab(cron_expr.strip(), timezone=tz)
        self._scheduler.add_job(
            func=_fire_job,
            trigger=trigger,
            args=[chat_id, job_id, "cron"],
            id=job_id,
            replace_existing=True,
        )
        logger.info(
            f"Scheduled cron job {job_id} ({cron_expr}, {timezone}) in chat {chat_id}"
        )

    def get_job_ids(self) -> set[str]:
        return {job.id for job in self._scheduler.get_jobs()}

    def cancel(self, job_id: str) -> bool:
        try:
            self._scheduler.remove_job(job_id)
            logger.info(f"Cancelled job {job_id}")
            return True
        except Exception:
            logger.warning(f"Job {job_id} not found for cancellation")
            return False
