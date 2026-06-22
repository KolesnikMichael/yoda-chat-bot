import asyncio
import datetime as dtm
import logging
import time
from collections.abc import Awaitable, Coroutine
from typing import Literal

from yoda.api.scheduler_api import SchedulerApi
from yoda.api.storage_api import StorageApi
from yoda.mind.data.maintenance_settings import MaintenanceSettings
from yoda.mind.memory.compression_apply_core import CompressionApplyCore
from yoda.mind.memory.compression_core import CompressionCore
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.data.compression_snapshot import CompressionTransformResult
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.inline_summary_envelope import InlineSummaryEnvelope
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.memory import MemoryCore, MemoryProvider
from yoda.mind.memory.summarizer import SummarizerCore, SummarizerProvider

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
        summarizer_provider: SummarizerProvider,
    ) -> None:
        self._storage_api = storage_api
        self._scheduler_api = scheduler_api
        self._memory_provider = memory_provider
        self._compression_settings = compression_settings
        self._summarizer_provider = summarizer_provider
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
            if "size" in triggers:
                await self._run_compression_apply(conversation, "size", chat_type)
            elif "timeout" in triggers:
                await self._run_compression_apply(conversation, "timeout", chat_type)

    async def _run_compression_apply(
        self,
        conversation: Conversation,
        trigger: Literal["size", "timeout"],
        chat_type: str,
    ) -> None:
        chat_id = conversation.chat_id
        snapshot = await self._memory_provider.take_compression_snapshot(chat_id)
        if snapshot is None:
            return

        if trigger == "size":
            split = CompressionCore.select_size_trigger_window(snapshot.copy.messages)
        else:
            split = CompressionCore.select_timeout_trigger_window(
                snapshot.copy.messages,
                self._compression_settings,
                chat_type,
                self._tick_seconds,
            )
        if split is None:
            return

        chunk_start, chunk_end, chunk = CompressionApplyCore.slice_compressible_chunk(
            snapshot.copy.messages,
            split,
        )
        if chunk_start >= chunk_end:
            return

        stripped_chunk, removed_users = CompressionApplyCore.strip_user_introductions(chunk)
        if not stripped_chunk:
            return
        CompressionApplyCore.assert_removed_users_invariant(stripped_chunk, removed_users)

        chunk_visible_count = CompressionApplyCore.visible_count(stripped_chunk)
        start_id = CompressionApplyCore.chunk_boundary_message_id(
            snapshot.copy.messages,
            chunk_start,
        )
        end_id = CompressionApplyCore.chunk_boundary_message_id(
            snapshot.copy.messages,
            chunk_end - 1,
        )

        participants = SummarizerCore.extract_participants(stripped_chunk)
        participant_profiles = {
            user_id: await self._memory_provider.get_user_profile(user_id, chat_id)
            for user_id in participants
        }

        try:
            summarizer_result = await self._summarizer_provider.summarise(
                stripped_chunk,
                participant_profiles,
            )
        except Exception:
            logger.warning(
                "compression aborted: summariser failure chat_id=%s",
                chat_id,
                exc_info=True,
            )
            return

        for user_id, delta in summarizer_result.profile_updates.items():
            await self._memory_provider.update_user_profile(user_id, chat_id, delta)

        summary_id = CompressionApplyCore.compute_summary_id(
            chat_id,
            snapshot.snapshot_ts,
            start_id,
            end_id,
        )
        from_ts, to_ts = CompressionApplyCore.first_last_visible_timestamps(stripped_chunk)
        added_at = dtm.datetime.fromtimestamp(snapshot.snapshot_ts, dtm.UTC).isoformat()
        envelope = InlineSummaryEnvelope(
            summary_id=summary_id,
            added_at=added_at,
            content_from_ts=from_ts,
            content_to_ts=to_ts,
            skills=summarizer_result.skills,
            topics=summarizer_result.topics,
            text=summarizer_result.summary,
        )

        working_copy = snapshot.copy
        CompressionApplyCore.replace_chunk_with_summary(
            working_copy,
            chunk_start,
            chunk_end,
            envelope,
        )
        outbox_entries, evicted_audit = CompressionApplyCore.evict_summaries_fifo(
            working_copy,
            self._compression_settings.max_summary_count,
            snapshot.snapshot_ts,
            summaries_added=1,
        )
        working_copy.pending_vectorization.extend(outbox_entries)

        profiles_after_update: dict[int, UserProfile] = {}
        for user_id in removed_users:
            profiles_after_update[user_id] = await self._memory_provider.get_user_profile(
                user_id,
                chat_id,
            )

        def intro_text_for_user_id(user_id: int) -> str:
            profile = profiles_after_update.get(user_id, UserProfile())
            return MemoryCore.format_user_profile_snapshot(profile)

        CompressionApplyCore.refresh_removed_users_on_copy(
            working_copy,
            chunk_start,
            removed_users,
            intro_text_for_user_id,
        )
        CompressionApplyCore.apply_derived_fields(
            working_copy,
            snapshot.snapshot_ts,
            chunk_visible_count,
        )

        audit_entry = CompressionApplyCore.build_compression_audit_entry(
            snapshot.snapshot_ts,
            summary_id,
            chunk_visible_count,
            from_ts,
            to_ts,
            evicted_audit,
        )

        transform_result = CompressionTransformResult(
            copy=working_copy,
            removed_users=removed_users,
            audit_entry=audit_entry,
            chunk_visible_count=chunk_visible_count,
        )
        await self._memory_provider.commit_compression(
            chat_id,
            snapshot,
            transform_result,
            removed_users,
            intro_text_for_user_id,
        )
        logger.debug("compression applied: chat_id=%s trigger=%s", chat_id, trigger)

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
