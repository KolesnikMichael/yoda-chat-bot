import asyncio
import copy
import datetime as dtm
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from .data.chat import Chat
from .data.compression_snapshot import CompressionSnapshot, CompressionTransformResult
from .data.conversation import Conversation
from .data.message import Message, MessageKind
from .data.summary_outbox_entry import SummaryOutboxEntry
from .data.system_prompt import DEFAULT_SYSTEM_PROMPT
from .data.user import User
from .data.user_profile import UserProfile
from .migration import MigrationError, migrate

logger = logging.getLogger(__name__)

# Ephemeral Redis STRING: written on graceful shutdown, consumed and deleted on next startup.
CONVERSATION_STASH_REDIS_KEY = "conversation_stash"
CONVERSATION_STASH_SCHEMA_VERSION = 3

KNOWN_TASK_RESULT_PREFIXES = (
    "SCHEDULED REMINDER:",
    "SCHEDULED TASK FAILED:",
    "Agent completed a task",
    "Ask the user (rephrase naturally",
)

VISIBLE_KINDS: frozenset[MessageKind] = frozenset({"user", "assistant"})

PROFILE_DELTA_KEYS = frozenset({
    "interests_to_add",
    "facts_to_add",
    "skill_preferences_to_add",
})


def _append_case_insensitive(target: list[str], items: list[str]) -> None:
    existing_lower = {s.lower() for s in target}
    for item in items:
        if item.lower() not in existing_lower:
            target.append(item)
            existing_lower.add(item.lower())


class MemoryCore:
    @staticmethod
    def conversation_key(chat_id: int) -> str:
        return str(chat_id)

    @staticmethod
    def parse_message_timestamp(timestamp: str) -> float:
        if not timestamp:
            return 0.0
        normalized = timestamp.replace("Z", "+00:00")
        if " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T", 1)
        try:
            return dtm.datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def infer_kind(
        msg: dict,
        *,
        is_first: bool,
        chat_id: int,
        message_index: int,
    ) -> MessageKind:
        role = msg.get("role", "")
        text = msg.get("text", "")
        user_id = msg.get("user_id")

        if role == "assistant":
            return "assistant"
        if is_first:
            return "prompt"
        if user_id is not None:
            return "user"
        if role == "system":
            for prefix in KNOWN_TASK_RESULT_PREFIXES:
                if text.startswith(prefix):
                    return "task_result"
            raise MigrationError(
                chat_id=chat_id,
                message_index=message_index,
                text_prefix=text[:80],
            )
        return "user"

    @staticmethod
    def add_conversation_line(
        conversation: Conversation | None,
        chat_id: int,
        *,
        kind: MessageKind,
        role: str,
        line: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[Conversation, list[dict]]:
        if not conversation:
            key = MemoryCore.conversation_key(chat_id)
            logger.info(f"Starting new conversation in chat {key}")
            conversation = Conversation(chat_id=chat_id)

        conversation.ensure_system_prompt(system_prompt)
        conversation.add_message(
            kind=kind,
            role=role,
            text=line,
            timestamp=timestamp,
            message_id=message_id,
            user_id=user_id,
        )
        if kind in VISIBLE_KINDS:
            conversation.visible_messages += 1
            parsed = MemoryCore.parse_message_timestamp(timestamp)
            conversation.last_visible_at = max(conversation.last_visible_at, parsed)
        return conversation, conversation.to_llm_messages()

    @staticmethod
    def conversations_to_stash_dict(conversations: dict[str, Conversation]) -> dict:
        wire_conversations: dict[str, dict] = {}
        for key, conv in conversations.items():
            wire_conversations[key] = {
                "chat_id": conv.chat_id,
                "messages": [asdict(m) for m in conv.messages],
                "last_visible_at": conv.last_visible_at,
                "last_compressed_at": conv.last_compressed_at,
                "visible_messages": conv.visible_messages,
                "introduced_users": sorted(conv.introduced_users),
                "pending_vectorization": [
                    asdict(entry) for entry in conv.pending_vectorization
                ],
            }
        return {
            "schema_version": CONVERSATION_STASH_SCHEMA_VERSION,
            "conversations": wire_conversations,
        }

    @staticmethod
    def stash_dict_to_conversations(data: dict) -> dict[str, Conversation]:
        raw = data.get("conversations", {})
        if not isinstance(raw, dict):
            return {}
        out: dict[str, Conversation] = {}
        for payload in raw.values():
            if not isinstance(payload, dict):
                continue
            chat_id = int(payload["chat_id"])
            messages = [
                Message(**{k: v for k, v in msg.items()
                           if k in Message.__dataclass_fields__})
                for msg in payload.get("messages", [])
                if isinstance(msg, dict)
            ]
            pending_raw = payload.get("pending_vectorization", [])
            pending_vectorization = [
                SummaryOutboxEntry(**entry)
                for entry in pending_raw
                if isinstance(entry, dict)
            ]
            introduced_raw = payload.get("introduced_users", [])
            introduced_users = (
                set(int(uid) for uid in introduced_raw)
                if isinstance(introduced_raw, list)
                else set()
            )
            out[MemoryCore.conversation_key(chat_id)] = Conversation(
                chat_id=chat_id,
                messages=messages,
                last_visible_at=float(payload.get("last_visible_at", 0.0)),
                last_compressed_at=float(payload.get("last_compressed_at", 0.0)),
                visible_messages=int(payload.get("visible_messages", 0)),
                introduced_users=introduced_users,
                pending_vectorization=pending_vectorization,
            )
        return out

    @staticmethod
    def apply_profile_updates(current: UserProfile, fields: dict) -> UserProfile:
        """Return a new UserProfile with delta merges and replace setattr applied.

        Processing order:
        1. Delta keys (append-with-case-insensitive-dedup); keys not stored on profile.
        2. Keys in UserProfile.__dataclass_fields__ → setattr (replace semantics).
        3. Unknown keys → ignored.
        """
        profile = copy.deepcopy(current)

        if "interests_to_add" in fields:
            _append_case_insensitive(profile.interests, fields["interests_to_add"])
        if "facts_to_add" in fields:
            _append_case_insensitive(profile.facts, fields["facts_to_add"])
        if "skill_preferences_to_add" in fields:
            for skill_name, items in fields["skill_preferences_to_add"].items():
                bucket = profile.skill_preferences.setdefault(skill_name, [])
                _append_case_insensitive(bucket, items)

        for k, v in fields.items():
            if k in PROFILE_DELTA_KEYS:
                continue
            if k in UserProfile.__dataclass_fields__:
                setattr(profile, k, v)

        return profile

    @staticmethod
    def format_user_profile_snapshot(profile: UserProfile) -> str:
        """Return deterministic introduction text; excludes schema_version and updated_on."""

        def _scalar(value: str) -> str:
            return value if value else "(not set)"

        lines = [
            "User profile snapshot:",
            f"Preferred name: {_scalar(profile.preferred_name)}",
            f"Gender: {_scalar(profile.gender)}",
            f"Location: {_scalar(profile.location)}",
            f"Timezone: {_scalar(profile.timezone)}",
            f"Occupation: {_scalar(profile.occupation)}",
            "Interests:",
        ]
        if profile.interests:
            lines.extend(f"- {item}" for item in profile.interests)
        else:
            lines.append("  (none)")

        lines.append("Facts:")
        if profile.facts:
            lines.extend(f"- {item}" for item in profile.facts)
        else:
            lines.append("  (none)")

        lines.append("Skill preferences:")
        skills_with_items = [
            (name, items)
            for name, items in sorted(profile.skill_preferences.items())
            if items
        ]
        for skill_name, items in skills_with_items:
            lines.append(f"  {skill_name}:")
            lines.extend(f"  - {item}" for item in items)

        all_empty = (
            not profile.preferred_name
            and not profile.gender
            and not profile.location
            and not profile.timezone
            and not profile.occupation
            and not profile.interests
            and not profile.facts
            and not skills_with_items
        )
        if all_empty:
            lines.append("(no profile information stored yet)")

        return "\n".join(lines)

    @staticmethod
    def conversation_needs_introduction_reconciliation(conversation: Conversation) -> bool:
        has_user = any(msg.kind == "user" for msg in conversation.messages)
        has_introduction = any(
            msg.kind == "user_introduction" for msg in conversation.messages
        )
        return (
            has_user
            and bool(conversation.introduced_users)
            and not has_introduction
        )

    @staticmethod
    def rebuild_introduced_users(conversation: Conversation) -> None:
        conversation.introduced_users = {
            msg.user_id
            for msg in conversation.messages
            if msg.kind == "user_introduction" and msg.user_id is not None
        }

    @staticmethod
    def ensure_user_introductions_in_range(
        conversation: Conversation,
        start: int,
        end: int,
        intro_text_for_user_id: Callable[[int], str],
    ) -> None:
        first_user_index: dict[int, int] = {}
        for index in range(start, end):
            msg = conversation.messages[index]
            if msg.kind != "user" or msg.user_id is None:
                continue
            if msg.user_id not in first_user_index:
                first_user_index[msg.user_id] = index

        insertions: list[tuple[int, int]] = []
        for user_id, index in first_user_index.items():
            if index > 0:
                prev = conversation.messages[index - 1]
                if prev.kind == "user_introduction" and prev.user_id == user_id:
                    continue
            insertions.append((index, user_id))

        for index, user_id in sorted(insertions, key=lambda item: item[0], reverse=True):
            conversation.messages.insert(
                index,
                Message(
                    role="system",
                    kind="user_introduction",
                    text=intro_text_for_user_id(user_id),
                    user_id=user_id,
                ),
            )
            conversation.introduced_users.add(user_id)


class MemoryProvider:
    def __init__(self, storage_api):
        self._storage_api = storage_api
        self._conversations: dict[str, Conversation] = {}
        self._compression_locks: dict[int, asyncio.Lock] = {}

    @asynccontextmanager
    async def conversation_lock(self, chat_id: int) -> AsyncIterator[None]:
        if chat_id not in self._compression_locks:
            self._compression_locks[chat_id] = asyncio.Lock()
        async with self._compression_locks[chat_id]:
            yield

    async def take_compression_snapshot(self, chat_id: int) -> CompressionSnapshot | None:
        async with self.conversation_lock(chat_id):
            live = self.get_conversation(chat_id)
            if live is None:
                return None
            return CompressionSnapshot(
                n_old=len(live.messages),
                copy=copy.deepcopy(live),
                snapshot_ts=time.time(),
            )

    async def append_chat_history_event(self, chat_id: int, event: dict) -> None:
        raw = await self._storage_api.hget("chats", str(chat_id))
        if raw:
            data = migrate("chats", json.loads(raw))
            chat = Chat(**{k: v for k, v in data.items() if k in Chat.__dataclass_fields__})
        else:
            chat = Chat()
        chat.history.append(event)
        chat.updated_on = dtm.datetime.now(dtm.UTC).isoformat()
        await self._storage_api.hset("chats", str(chat_id), json.dumps(chat.to_dict()))

    async def commit_compression(
        self,
        chat_id: int,
        snapshot: CompressionSnapshot,
        result: CompressionTransformResult,
        removed_users: set[int],
        intro_text_for_user_id: Callable[[int], str],
    ) -> None:
        from .compression_apply_core import CompressionApplyCore

        async with self.conversation_lock(chat_id):
            live = self.get_conversation(chat_id)
            if live is None:
                raise ValueError(f"No conversation for chat_id={chat_id}")
            if len(live.messages) < snapshot.n_old:
                raise ValueError(
                    f"Compression graft tripwire: len(live.messages)={len(live.messages)} "
                    f"< n_old={snapshot.n_old} for chat_id={chat_id}"
                )
            new_arrivals = live.messages[snapshot.n_old:]
            live.messages = result.copy.messages + new_arrivals
            live.last_compressed_at = result.copy.last_compressed_at
            live.visible_messages = (
                result.copy.visible_messages
                + CompressionApplyCore.visible_count(new_arrivals)
            )
            live.introduced_users = set(result.copy.introduced_users)
            copy_end_index = len(result.copy.messages)
            CompressionApplyCore.reconcile_arrivals_introductions(
                live,
                copy_end_index,
                removed_users,
                intro_text_for_user_id,
            )
            live.pending_vectorization = list(result.copy.pending_vectorization)
            self.save_conversation(live)
            await self.append_chat_history_event(chat_id, result.audit_entry)

    async def append_message(
        self,
        conversation: Conversation | None,
        chat_id: int,
        *,
        kind: MessageKind,
        role: str,
        line: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[Conversation, list[dict]]:
        async with self.conversation_lock(chat_id):
            conversation, _ = MemoryCore.add_conversation_line(
                conversation=conversation,
                chat_id=chat_id,
                kind=kind,
                role=role,
                line=line,
                system_prompt=system_prompt,
                timestamp=timestamp,
                message_id=message_id,
                user_id=user_id,
            )
            return conversation, conversation.to_llm_messages()

    def get_conversation(self, chat_id: int) -> Conversation | None:
        key = MemoryCore.conversation_key(chat_id)
        return self._conversations.get(key)

    def save_conversation(self, conversation: Conversation) -> None:
        key = MemoryCore.conversation_key(conversation.chat_id)
        self._conversations[key] = conversation

    def forget_conversation(self, chat_id: int) -> None:
        key = MemoryCore.conversation_key(chat_id)
        self._conversations.pop(key, None)

    def iter_conversations(self) -> Iterator[Conversation]:
        return iter(self._conversations.values())

    async def get_chat_type(self, chat_id: int) -> str:
        raw = await self._storage_api.hget("chats", str(chat_id))
        if raw is None:
            raise ValueError(f"Missing chat_type for chat_id={chat_id}")
        data = migrate("chats", json.loads(raw))
        chat = Chat(**{k: v for k, v in data.items() if k in Chat.__dataclass_fields__})
        if not chat.chat_type:
            raise ValueError(f"Missing chat_type for chat_id={chat_id}")
        return chat.chat_type

    async def append_conversation_line(
        self,
        conversation: Conversation | None,
        chat_id: int,
        *,
        kind: MessageKind,
        role: str,
        line: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        timestamp: str = "",
        message_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[Conversation, list[dict]]:
        async with self.conversation_lock(chat_id):
            profile_text: str | None = None
            introduced_users = conversation.introduced_users if conversation else set()
            needs_introduction = (
                kind == "user"
                and user_id is not None
                and user_id not in introduced_users
            )
            if needs_introduction:
                profile = await self.get_user_profile(user_id, chat_id)
                profile_text = MemoryCore.format_user_profile_snapshot(profile)

            conversation, _ = MemoryCore.add_conversation_line(
                conversation=conversation,
                chat_id=chat_id,
                kind=kind,
                role=role,
                line=line,
                system_prompt=system_prompt,
                timestamp=timestamp,
                message_id=message_id,
                user_id=user_id,
            )

            if needs_introduction and profile_text is not None and user_id is not None:
                user_index = len(conversation.messages) - 1
                MemoryCore.ensure_user_introductions_in_range(
                    conversation,
                    user_index,
                    user_index + 1,
                    lambda uid, text=profile_text: text,
                )

            return conversation, conversation.to_llm_messages()

    async def _reconcile_user_introductions_if_needed(
        self,
        conversation: Conversation,
    ) -> None:
        if not MemoryCore.conversation_needs_introduction_reconciliation(conversation):
            return

        user_ids = {
            msg.user_id
            for msg in conversation.messages
            if msg.kind == "user" and msg.user_id is not None
        }
        snapshots: dict[int, str] = {}
        for uid in user_ids:
            profile = await self.get_user_profile(uid, conversation.chat_id)
            snapshots[uid] = MemoryCore.format_user_profile_snapshot(profile)

        empty_snapshot = MemoryCore.format_user_profile_snapshot(UserProfile())
        end = len(conversation.messages)
        MemoryCore.ensure_user_introductions_in_range(
            conversation,
            0,
            end,
            lambda uid: snapshots.get(uid, empty_snapshot),
        )
        MemoryCore.rebuild_introduced_users(conversation)

    async def save_conversation_stash(self) -> None:
        if not self._conversations:
            await self._storage_api.delete(CONVERSATION_STASH_REDIS_KEY)
            logger.info("Conversation stash: no conversations to save, key removed")
            return
        payload = MemoryCore.conversations_to_stash_dict(self._conversations)
        raw = json.dumps(payload)
        await self._storage_api.set(CONVERSATION_STASH_REDIS_KEY, raw)
        logger.info(f"Conversation stash: saved {len(self._conversations)} chat(s) to Redis")

    async def restore_conversation_stash(self) -> None:
        raw = await self._storage_api.get(CONVERSATION_STASH_REDIS_KEY)
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.exception("Conversation stash: invalid JSON, key left in place")
            return
        if not isinstance(data, dict):
            logger.error("Conversation stash: root must be an object, key left in place")
            return
        try:
            data = migrate("conversation_stash", data)
            restored = MemoryCore.stash_dict_to_conversations(data)
        except Exception:
            logger.exception(
                "Conversation stash: restore failed, key left in place for inspection"
            )
            return
        for conversation in restored.values():
            await self._reconcile_user_introductions_if_needed(conversation)
        self._conversations = restored
        await self._storage_api.delete(CONVERSATION_STASH_REDIS_KEY)
        logger.info(f"Conversation stash: restored {len(restored)} chat(s), key removed")

    async def update_sender_info(self, user_id: int, user_info: dict) -> None:
        raw = await self._storage_api.hget("users", str(user_id))
        if raw:
            data = migrate("users", json.loads(raw))
            user = User(**{k: v for k, v in data.items() if k in User.__dataclass_fields__})
        else:
            user = User(known_since=user_info.get("last_active", ""))
            logger.info(f"Registered user {user_id}")

        for field in ("username", "first_name", "last_name", "last_active"):
            if field in user_info:
                setattr(user, field, user_info[field])

        await self._storage_api.hset("users", str(user_id), json.dumps(user.to_dict()))

    async def update_chat_info(self, chat_id: int, chat_type: str, last_active: str) -> None:
        raw = await self._storage_api.hget("chats", str(chat_id))
        if raw:
            data = migrate("chats", json.loads(raw))
            chat = Chat(**{k: v for k, v in data.items() if k in Chat.__dataclass_fields__})
        else:
            chat = Chat(chat_type=chat_type)
            logger.info(f"Registered chat {chat_id}")

        chat.last_active = last_active
        chat.updated_on = dtm.datetime.now(dtm.UTC).isoformat()
        await self._storage_api.hset("chats", str(chat_id), json.dumps(chat.to_dict()))

    async def get_user_profile(self, user_id: int, chat_id: int) -> UserProfile:
        user_profile_id = f"{user_id}@{chat_id}"
        raw = await self._storage_api.hget("user_profiles", user_profile_id)
        if raw:
            data = migrate("user_profiles", json.loads(raw))
            return UserProfile(
                **{k: v for k, v in data.items() if k in UserProfile.__dataclass_fields__}
            )
        return UserProfile()

    async def update_user_profile(self, user_id: int, chat_id: int, user_profile: dict) -> None:
        user_profile_id = f"{user_id}@{chat_id}"
        raw = await self._storage_api.hget("user_profiles", user_profile_id)

        if raw:
            data = migrate("user_profiles", json.loads(raw))
            current = UserProfile(
                **{k: v for k, v in data.items() if k in UserProfile.__dataclass_fields__}
            )
        else:
            current = UserProfile()

        current = MemoryCore.apply_profile_updates(current, user_profile)

        current.updated_on = dtm.datetime.now(dtm.UTC).isoformat()
        await self._storage_api.hset("user_profiles", user_profile_id, json.dumps(current.to_dict()))
