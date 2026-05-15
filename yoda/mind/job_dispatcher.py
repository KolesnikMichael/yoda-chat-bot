from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.agent.tools.job_keys import active_jobs_key

if TYPE_CHECKING:
    from yoda.mind.mind import Mind

logger = logging.getLogger(__name__)


class JobDispatcher:
    def __init__(
        self,
        storage_api: StorageApi,
        scheduler_api: SchedulerApi,
        mind: Mind,
    ):
        self._storage_api = storage_api
        self._scheduler_api = scheduler_api
        self._mind = mind

    async def fire(self, chat_id: int, job_id: str) -> None:
        raw = await self._storage_api.hget(active_jobs_key(chat_id), job_id)
        if raw is None:
            logger.warning(
                "Job %s missing payload for chat %s, removing from scheduler",
                job_id,
                chat_id,
            )
            self._scheduler_api.cancel(job_id)
            return

        data = json.loads(raw)
        kind = data.get("kind", "message")

        if kind == "message":
            await self._mind.deliver_scheduled_reminder(
                chat_id=chat_id,
                user_id=data.get("user_id", 0),
                reminder_text=data.get("message_text", data.get("description", "")),
            )
            return

        if kind == "task":
            try:
                await self._mind.execute_scheduled_task(
                    chat_id=chat_id,
                    user_id=data.get("user_id", 0),
                    skill_name=data["skill_name"],
                    distilled_task=data["distilled_task"],
                )
            except Exception:
                logger.exception(
                    "Scheduled task failed for job %s in chat %s",
                    job_id,
                    chat_id,
                )
                await self._mind.notify_scheduled_failure(
                    chat_id,
                    "A scheduled task could not be completed this time.",
                )
            return

        logger.error("Unknown job kind %r for job %s", kind, job_id)
