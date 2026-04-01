import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_delivery_callback: Callable[..., Coroutine[Any, Any, None]] | None = None
_cleanup_callback: Callable[..., Coroutine[Any, Any, None]] | None = None


async def _fire_job(chat_id: int, user_id: int, text: str, job_id: str, job_type: str) -> None:
    if _delivery_callback is None:
        logger.error("Delivery callback not set, cannot deliver scheduled message")
        return
    await _delivery_callback(chat_id, user_id, text)
    if _cleanup_callback and job_type == "once":
        await _cleanup_callback(chat_id, job_id)


class SchedulerApi:
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        jobstore = RedisJobStore(host=redis_host, port=redis_port, db=redis_db)
        self._scheduler = AsyncIOScheduler(jobstores={"default": jobstore})

    def set_delivery_callback(
        self, callback: Callable[..., Coroutine[Any, Any, None]]
    ) -> None:
        global _delivery_callback
        _delivery_callback = callback

    def set_cleanup_callback(
        self, callback: Callable[..., Coroutine[Any, Any, None]]
    ) -> None:
        global _cleanup_callback
        _cleanup_callback = callback

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")

    def schedule_once(
        self,
        job_id: str,
        run_date: datetime,
        chat_id: int,
        user_id: int,
        text: str,
    ) -> None:
        self._scheduler.add_job(
            func=_fire_job,
            trigger="date",
            run_date=run_date,
            args=[chat_id, user_id, text, job_id, "once"],
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled one-time job {job_id} at {run_date} for user {user_id} in chat {chat_id}")

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
