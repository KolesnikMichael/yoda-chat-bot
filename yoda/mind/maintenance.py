import asyncio
import logging
import time
from collections.abc import Awaitable, Coroutine

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.data.maintenance_settings import MaintenanceSettings
from yoda.mind.memory.compression_core import CompressionCore
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.memory import MemoryProvider

logger = logging.getLogger(__name__)

RECONCILE_EVERY_N_TICKS = 24


async def reconcile_active_jobs(
    storage_api: StorageApi,
    scheduler_api: SchedulerApi,
) -> int:
    live_ids = scheduler_api.get_job_ids()
    all_keys = await storage_api.keys("active_jobs:*")
    removed = 0
    for key in all_keys:
        entries = await storage_api.hgetall(key)
        for job_id in entries:
            if job_id not in live_ids:
                await storage_api.hdel(key, job_id)
                removed += 1
    if removed:
        logger.info(f"Reconciled active_jobs: removed {removed} stale entries")
    return removed


class Maintenance:
    def __init__(
        self,
        *,
        storage_api: StorageApi,
        scheduler_api: SchedulerApi,
        memory_provider: MemoryProvider,
        compression_settings: ChatCompressionSettings,
        maintenance_settings: MaintenanceSettings,
    ) -> None:
        self._storage_api = storage_api
        self._scheduler_api = scheduler_api
        self._memory_provider = memory_provider
        self._compression_settings = compression_settings
        self._tick_seconds = float(maintenance_settings.tick_minutes * 60)
        self._tick_count = 0
        self._loop_task: asyncio.Task[None] | None = None

    async def run_initial_pass(self) -> None:
        await reconcile_active_jobs(self._storage_api, self._scheduler_api)

    def start(self) -> None:
        self._loop_task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        task = self._loop_task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _tick_loop(self) -> None:
        while True:
            self._tick_count += 1
            await self._run_subroutine(
                "compress_conversations",
                self.compress_conversations(),
            )
            await self._run_subroutine(
                "flush_summary_outbox",
                self.flush_summary_outbox(),
            )
            if self._tick_count % RECONCILE_EVERY_N_TICKS == 0:
                await self._run_subroutine(
                    "reconcile_active_jobs",
                    reconcile_active_jobs(self._storage_api, self._scheduler_api),
                )
            await asyncio.sleep(self._tick_seconds)

    async def compress_conversations(self) -> None:
        now = time.time()
        for conversation in self._memory_provider.iter_conversations():
            chat_type = await self._memory_provider.get_chat_type(conversation.chat_id)
            triggers: list[str] = []
            if CompressionCore.should_fire_size_trigger(
                conversation.visible_messages,
                self._compression_settings,
            ):
                triggers.append("size")
            if CompressionCore.should_evaluate_timeout_trigger(
                conversation.visible_messages,
                conversation.last_visible_at,
                conversation.last_compressed_at,
                now,
                self._compression_settings,
                chat_type,
                self._tick_seconds,
            ):
                triggers.append("timeout")
            if triggers:
                logger.debug(
                    "compression trigger candidate: chat_id=%s triggers=%s",
                    conversation.chat_id,
                    triggers,
                )

    async def flush_summary_outbox(self) -> None:
        return None

    async def _run_subroutine(
        self,
        name: str,
        coro: Coroutine[None, None, None] | Awaitable[int],
    ) -> None:
        try:
            await coro
        except Exception:
            logger.warning("%s failed", name, exc_info=True)
