import json
from dataclasses import asdict
from pathlib import Path

import pytest

from yoda.mind.affect import AffectCore
from yoda.mind.cognition import CognitionCore
from yoda.mind.memory.data.chat_compression_settings import ChatCompressionSettings
from yoda.mind.memory.data.summary_outbox_entry import SummaryOutboxEntry
from yoda.mind.memory.data.system_prompt import DEFAULT_SYSTEM_PROMPT
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.memory.memory import (
    CONVERSATION_STASH_REDIS_KEY,
    CONVERSATION_STASH_SCHEMA_VERSION,
    MemoryCore,
    MemoryProvider,
)
from yoda.mind.memory.migration import MigrationError, migrate


class FakeStorageApi:
    def __init__(self):
        self.data = {}
        self.strings: dict[str, str] = {}

    async def hget(self, key: str, field: str):
        return self.data.get(key, {}).get(field)

    async def hset(self, key: str, field: str, value: str):
        bucket = self.data.setdefault(key, {})
        bucket[field] = value
        return 1

    async def get(self, key: str):
        return self.strings.get(key)

    async def set(self, key: str, value: str):
        self.strings[key] = value
        return True

    async def delete(self, key: str):
        return 1 if self.strings.pop(key, None) is not None else 0


@pytest.mark.asyncio
async def test_update_sender_info_creates_user():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)
    user_info = {
        "username": "luke",
        "first_name": "Luke",
        "last_name": "Skywalker",
        "last_active": "2026-02-20T00:00:00",
    }

    await memory_provider.update_sender_info(user_id=1, user_info=user_info)

    saved_user = json.loads(storage.data["users"]["1"])
    assert saved_user["username"] == "luke"
    assert saved_user["known_since"] == "2026-02-20T00:00:00"
    assert saved_user["schema_version"] == 2


@pytest.mark.asyncio
async def test_update_sender_info_migrates_v1_user():
    storage = FakeStorageApi()
    storage.data["users"] = {
        "1": json.dumps({
            "username": "luke",
            "first_name": "Luke",
            "last_name": "Skywalker",
            "language_code": "en",
            "last_active": "2026-01-01T00:00:00",
            "known_since": "2026-01-01T00:00:00",
        })
    }
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_sender_info(
        user_id=1,
        user_info={"username": "luke", "first_name": "Luke",
                    "last_name": "Skywalker", "last_active": "2026-02-20T00:00:00"},
    )

    saved_user = json.loads(storage.data["users"]["1"])
    assert "language_code" not in saved_user
    assert saved_user["schema_version"] == 2
    assert saved_user["last_active"] == "2026-02-20T00:00:00"


@pytest.mark.asyncio
async def test_update_chat_info_creates_chat():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_chat_info(
        chat_id=1,
        chat_type="private",
        last_active="2026-02-20T00:00:00",
    )

    saved_chat = json.loads(storage.data["chats"]["1"])
    assert saved_chat["chat_type"] == "private"
    assert saved_chat["schema_version"] == 4
    assert saved_chat["updated_on"] != ""
    assert "conversation" not in saved_chat
    assert "users" not in saved_chat


@pytest.mark.asyncio
async def test_update_chat_info_migrates_v1_chat():
    storage = FakeStorageApi()
    storage.data["chats"] = {
        "1": json.dumps({"schema_version": 1})
    }
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_chat_info(
        chat_id=1, chat_type="private", last_active="2026-02-20T00:00:00")

    saved_chat = json.loads(storage.data["chats"]["1"])
    assert saved_chat["schema_version"] == 4
    assert "conversation" not in saved_chat
    assert "users" not in saved_chat


@pytest.mark.asyncio
async def test_get_user_profile_migrates_v1():
    storage = FakeStorageApi()
    storage.data["user_profiles"] = {
        "1@1": json.dumps({
            "nickname": "Luke",
            "preferred_language": "en",
            "education": "Jedi Academy",
            "birthday": "19 BBY",
            "age": "23",
            "miscellaneous": ["Force-sensitive"],
            "schema_version": 1,
        })
    }
    memory_provider = MemoryProvider(storage_api=storage)

    profile = await memory_provider.get_user_profile(user_id=1, chat_id=1)

    assert profile.preferred_name == "Luke"
    assert profile.facts == ["Force-sensitive"]
    assert not hasattr(profile, "nickname")
    assert not hasattr(profile, "preferred_language")


def test_add_conversation_line_initializes_system_prompt():
    conversation = None

    conversation, messages = MemoryCore.add_conversation_line(
        conversation=conversation,
        chat_id=11,
        kind="user",
        role="user",
        line="Hello there",
        system_prompt="Reply as Yoda from Star Wars",
    )

    assert messages[0] == {"role": "system",
                           "content": "Reply as Yoda from Star Wars"}
    assert messages[1] == {"role": "user", "content": "Hello there"}
    assert conversation.messages[0].kind == "prompt"
    assert conversation.messages[1].kind == "user"


def test_message_to_llm_dict_excludes_kind():
    message = Message(role="user", kind="user", text="hello")
    assert message.to_llm_dict() == {"role": "user", "content": "hello"}
    assert "kind" not in message.to_llm_dict()


def test_summary_outbox_entry_roundtrip():
    entry = SummaryOutboxEntry(
        summary_id="s1",
        document="summary text",
        created_at=1718123456.789,
        chunk_start_message_id=1,
        chunk_end_message_id=5,
        chunk_visible_count=4,
        participants=[1, 2],
        skills=["web_search"],
        topics=["weather"],
        added_at="2026-06-12T00:00:00+00:00",
    )
    restored = SummaryOutboxEntry(**asdict(entry))
    assert restored == entry


def test_chat_compression_settings_from_dict():
    settings = ChatCompressionSettings.from_dict({
        "size_trigger_threshold": 300,
        "min_chunk_length": 30,
        "max_summary_count": 30,
        "gap_to_trigger_ratio": 0.5,
        "quiet_runs_before_compression": {"private": 8, "group": 10},
        "outbox_health_threshold": 10,
    })
    assert settings.size_trigger_threshold == 300
    assert settings.quiet_runs_before_compression.private == 8
    assert settings.quiet_runs_before_compression.group == 10


def test_chat_compression_settings_from_dict_missing_key_raises():
    with pytest.raises(ValueError, match="Missing required key: size_trigger_threshold"):
        ChatCompressionSettings.from_dict({})


def test_conversation_defaults_and_add_message_kind():
    conv = Conversation(chat_id=1)
    assert conv.last_visible_at == 0.0
    assert conv.last_compressed_at == 0.0
    assert conv.visible_messages == 0
    assert conv.introduced_users == set()
    assert conv.pending_vectorization == []

    conv.ensure_system_prompt("bootstrap")
    assert conv.messages[0].kind == "prompt"

    conv.add_message(kind="user", role="system", text="perceived", user_id=7)
    assert conv.messages[-1].kind == "user"


def test_parse_message_timestamp():
    assert MemoryCore.parse_message_timestamp("") == 0.0
    iso_ts = MemoryCore.parse_message_timestamp("2026-03-09T21:36:51+00:00")
    space_ts = MemoryCore.parse_message_timestamp("2026-03-09 21:36:51+00:00")
    assert iso_ts == space_ts
    assert iso_ts > 0.0


def test_add_conversation_line_visible_counters():
    conversation, _ = MemoryCore.add_conversation_line(
        conversation=None,
        chat_id=1,
        kind="user",
        role="system",
        line="hello",
        timestamp="2026-03-09 21:36:51+00:00",
        user_id=5,
    )
    assert conversation.visible_messages == 1
    assert conversation.last_visible_at == MemoryCore.parse_message_timestamp(
        "2026-03-09 21:36:51+00:00"
    )

    conversation, _ = MemoryCore.add_conversation_line(
        conversation=conversation,
        chat_id=1,
        kind="assistant",
        role="assistant",
        line="reply",
        timestamp="2026-03-09T22:00:00+00:00",
    )
    assert conversation.visible_messages == 2
    assert conversation.last_visible_at == MemoryCore.parse_message_timestamp(
        "2026-03-09T22:00:00+00:00"
    )


def test_add_conversation_line_non_visible_kind_no_counter_bump():
    conversation, _ = MemoryCore.add_conversation_line(
        conversation=None,
        chat_id=1,
        kind="task_result",
        role="system",
        line="Agent completed a task. Result: ok",
        timestamp="2026-03-09 21:36:51+00:00",
    )
    assert conversation.visible_messages == 0
    assert conversation.last_visible_at == 0.0
    assert conversation.last_compressed_at == 0.0
    assert conversation.introduced_users == set()


def test_conversations_to_stash_dict_v3_roundtrip():
    entry = SummaryOutboxEntry(
        summary_id="s1",
        document="doc",
        created_at=1.0,
        chunk_start_message_id=1,
        chunk_end_message_id=2,
        chunk_visible_count=2,
        participants=[7],
        skills=[],
        topics=[],
        added_at="2026-06-12T00:00:00+00:00",
    )
    conv = Conversation(
        chat_id=42,
        messages=[
            Message(role="system", kind="prompt", text="sys"),
            Message(role="user", kind="user", text="hi", user_id=7, message_id=1),
        ],
        last_visible_at=100.0,
        last_compressed_at=0.0,
        visible_messages=1,
        introduced_users={7, 9},
        pending_vectorization=[entry],
    )
    wire = MemoryCore.conversations_to_stash_dict({"42": conv})
    assert wire["schema_version"] == 3
    payload = wire["conversations"]["42"]
    assert payload["last_visible_at"] == 100.0
    assert payload["last_compressed_at"] == 0.0
    assert payload["visible_messages"] == 1
    assert payload["introduced_users"] == [7, 9]
    assert payload["pending_vectorization"] == [asdict(entry)]
    assert payload["messages"][0]["kind"] == "prompt"

    restored = MemoryCore.stash_dict_to_conversations(wire)["42"]
    assert restored.visible_messages == 1
    assert restored.introduced_users == {7, 9}
    assert restored.pending_vectorization[0].summary_id == "s1"


def test_migration_error_attributes():
    err = MigrationError(chat_id=9, message_index=2, text_prefix="UNKNOWN:")
    assert err.chat_id == 9
    assert err.message_index == 2
    assert err.text_prefix == "UNKNOWN:"


def test_infer_kind_cases():
    assert MemoryCore.infer_kind(
        {"role": "assistant", "text": "hi", "user_id": None},
        is_first=False, chat_id=1, message_index=1,
    ) == "assistant"
    assert MemoryCore.infer_kind(
        {"role": "system", "text": "bootstrap", "user_id": None},
        is_first=True, chat_id=1, message_index=0,
    ) == "prompt"
    assert MemoryCore.infer_kind(
        {"role": "system", "text": "On Luke sent", "user_id": 7},
        is_first=False, chat_id=1, message_index=1,
    ) == "user"
    assert MemoryCore.infer_kind(
        {"role": "system", "text": "SCHEDULED REMINDER: call mom", "user_id": None},
        is_first=False, chat_id=1, message_index=2,
    ) == "task_result"
    assert MemoryCore.infer_kind(
        {"role": "system", "text": "Agent completed a task. Tools: none", "user_id": None},
        is_first=False, chat_id=1, message_index=2,
    ) == "task_result"


def test_infer_kind_unknown_prefix_raises():
    with pytest.raises(MigrationError) as exc_info:
        MemoryCore.infer_kind(
            {"role": "system", "text": "UNKNOWN PREFIX", "user_id": None},
            is_first=False, chat_id=42, message_index=3,
        )
    err = exc_info.value
    assert err.chat_id == 42
    assert err.message_index == 3


def test_migrate_conversation_stash_v2_to_v3():
    data = {
        "schema_version": 2,
        "conversations": {
            "1": {
                "chat_id": 1,
                "messages": [
                    {"role": "system", "text": "bootstrap", "user_id": None, "timestamp": ""},
                    {
                        "role": "system",
                        "text": 'On 2026-03-09 Luke sent text message: "hi"',
                        "user_id": 7,
                        "timestamp": "2026-03-09 21:36:51+00:00",
                    },
                    {"role": "assistant", "text": "hello", "user_id": None, "timestamp": "2026-03-09 22:00:00+00:00"},
                    {"role": "system", "text": "Agent completed a task. Result: ok", "user_id": None, "timestamp": ""},
                ],
            },
        },
    }
    migrated = migrate("conversation_stash", data)
    assert migrated["schema_version"] == 3
    payload = migrated["conversations"]["1"]
    kinds = [m["kind"] for m in payload["messages"]]
    assert kinds == ["prompt", "user", "assistant", "task_result"]
    assert payload["visible_messages"] == 2
    assert payload["introduced_users"] == [7]
    assert payload["pending_vectorization"] == []


@pytest.mark.asyncio
async def test_conversation_stash_restore_unknown_prefix_leaves_key():
    storage = FakeStorageApi()
    storage.strings[CONVERSATION_STASH_REDIS_KEY] = json.dumps({
        "schema_version": 2,
        "conversations": {
            "1": {
                "chat_id": 1,
                "messages": [
                    {"role": "system", "text": "bootstrap", "user_id": None},
                    {"role": "system", "text": "UNKNOWN PREFIX", "user_id": None},
                ],
            },
        },
    })
    memory = MemoryProvider(storage_api=storage)
    await memory.restore_conversation_stash()
    assert CONVERSATION_STASH_REDIS_KEY in storage.strings
    assert memory.get_conversation(1) is None


def test_chat_compression_settings_matches_settings_json():
    settings_path = Path(__file__).resolve().parents[1] / "settings.json"
    block = json.loads(settings_path.read_text())["mind"]["memory"]["chat_compression"]
    settings = ChatCompressionSettings.from_dict(block)
    assert settings.size_trigger_threshold == 300
    assert settings.min_chunk_length == 30
    assert settings.max_summary_count == 30
    assert settings.gap_to_trigger_ratio == 0.5
    assert settings.quiet_runs_before_compression.private == 8
    assert settings.quiet_runs_before_compression.group == 8
    assert settings.outbox_health_threshold == 10


def test_determine_chat_type():
    assert CognitionCore.determine_chat_type(
        user_id=1, chat_id=1) == "private"
    assert CognitionCore.determine_chat_type(
        user_id=1, chat_id=2) == "group"


def test_process_reply_stub_single_part():
    parts = CognitionCore.process_reply("One reply")
    assert parts == [{"text": "One reply", "message_id": None}]


def test_build_system_prompt_private_chat():
    prompt = AffectCore.build_system_prompt(chat_type="private")

    assert DEFAULT_SYSTEM_PROMPT.strip() in prompt
    assert "== CONTEXT ==" in prompt
    assert "private Telegram chat, one-on-one" in prompt


def test_build_system_prompt_group_chat():
    prompt = AffectCore.build_system_prompt(chat_type="group")

    assert "group chat" in prompt
    assert "Address users by name" in prompt
    assert "private" not in prompt.split("== CONTEXT ==")[1]


# --- Migration unit tests ---

def test_migrate_users_v1_to_v2():
    data = {"username": "luke", "language_code": "en", "schema_version": 1}

    result = migrate("users", data)

    assert result["schema_version"] == 2
    assert "language_code" not in result
    assert result["username"] == "luke"


def test_migrate_users_without_schema_version():
    data = {"username": "luke", "language_code": "en"}

    result = migrate("users", data)

    assert result["schema_version"] == 2
    assert "language_code" not in result


def test_migrate_user_profiles_v1_to_v2():
    data = {
        "nickname": "Luke",
        "preferred_language": "en",
        "education": "Jedi Academy",
        "birthday": "19 BBY",
        "age": "23",
        "miscellaneous": ["Force-sensitive"],
        "schema_version": 1,
    }

    result = migrate("user_profiles", data)

    assert result["schema_version"] == 2
    assert result["preferred_name"] == "Luke"
    assert result["facts"] == ["Force-sensitive"]
    assert "nickname" not in result
    assert "preferred_language" not in result
    assert "education" not in result
    assert "birthday" not in result
    assert "age" not in result
    assert "miscellaneous" not in result


def test_migrate_chats_v1_to_v4():
    data = {"schema_version": 1}

    result = migrate("chats", data)

    assert result["schema_version"] == 4
    assert "conversation" not in result
    assert "users" not in result
    assert "history" in result
    assert "updated_on" in result


def test_migrate_chats_v2_to_v4():
    data = {
        "chat_type": "private",
        "history": [],
        "conversation": {"users": [42, 7], "messages": []},
        "schema_version": 2,
    }

    result = migrate("chats", data)

    assert result["schema_version"] == 4
    assert "users" not in result
    assert "conversation" not in result
    assert result["updated_on"] == ""


def test_migrate_chats_v3_to_v4_strips_users():
    data = {
        "chat_type": "group",
        "users": [1, 2, 3],
        "history": [],
        "updated_on": "2026-01-01T00:00:00",
        "schema_version": 3,
    }

    result = migrate("chats", data)

    assert result["schema_version"] == 4
    assert "users" not in result
    assert result["chat_type"] == "group"
    assert result["updated_on"] == "2026-01-01T00:00:00"


def test_migrate_noop_for_current_version():
    data = {"schema_version": 2, "username": "luke"}

    result = migrate("users", data)

    assert result == data


def test_conversations_to_stash_dict_roundtrip_core():
    conv = Conversation(
        chat_id=42,
        messages=[
            Message(role="system", kind="prompt", text="sys"),
            Message(
                role="user",
                kind="user",
                text="hi",
                message_id=100,
                user_id=7,
            ),
        ],
        visible_messages=1,
        last_visible_at=1.0,
    )
    convs = {MemoryCore.conversation_key(42): conv}
    wire = MemoryCore.conversations_to_stash_dict(convs)
    assert wire["schema_version"] == CONVERSATION_STASH_SCHEMA_VERSION
    payload = wire["conversations"]["42"]
    assert "last_visible_at" in payload
    assert "last_compressed_at" in payload
    assert "visible_messages" in payload
    assert "introduced_users" in payload
    assert "pending_vectorization" in payload
    restored = MemoryCore.stash_dict_to_conversations(wire)
    assert len(restored) == 1
    r = restored["42"]
    assert r.chat_id == 42
    assert len(r.messages) == 2
    assert r.messages[1].text == "hi"
    assert r.messages[1].message_id == 100
    assert r.messages[1].user_id == 7
    assert r.messages[1].kind == "user"


@pytest.mark.asyncio
async def test_conversation_stash_save_restore_deletes_redis_key():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    conv = Conversation(
        chat_id=1,
        messages=[Message(role="user", kind="user", text="yo", message_id=1, user_id=1)],
        visible_messages=1,
    )
    memory.save_conversation(conv)

    await memory.save_conversation_stash()
    assert CONVERSATION_STASH_REDIS_KEY in storage.strings

    memory2 = MemoryProvider(storage_api=storage)
    await memory2.restore_conversation_stash()
    assert CONVERSATION_STASH_REDIS_KEY not in storage.strings
    got = memory2.get_conversation(1)
    assert got is not None
    assert got.messages[0].text == "yo"


@pytest.mark.asyncio
async def test_conversation_stash_restore_missing_key_noop():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    await memory.restore_conversation_stash()
    assert storage.strings == {}


@pytest.mark.asyncio
async def test_conversation_stash_save_empty_deletes_key():
    storage = FakeStorageApi()
    storage.strings[CONVERSATION_STASH_REDIS_KEY] = '{"stale": true}'
    memory = MemoryProvider(storage_api=storage)
    await memory.save_conversation_stash()
    assert CONVERSATION_STASH_REDIS_KEY not in storage.strings


# --- Profile update tests (TASK-000) ---

def test_profile_update_interests_to_add_dedup_case_insensitive():
    current = UserProfile(interests=["Python"])
    updated = MemoryCore.apply_profile_updates(
        current, {"interests_to_add": ["python", "Rust"]}
    )
    assert updated.interests == ["Python", "Rust"]
    assert "interests_to_add" not in updated.to_dict()


def test_profile_update_facts_to_add_dedup_case_insensitive():
    current = UserProfile(facts=["Lives in SPb"])
    updated = MemoryCore.apply_profile_updates(
        current, {"facts_to_add": ["lives in spb", "Works remotely"]}
    )
    assert updated.facts == ["Lives in SPb", "Works remotely"]


def test_profile_update_skill_preferences_to_add():
    current = UserProfile(
        skill_preferences={"web_search": ["accuweather.com"]}
    )
    updated = MemoryCore.apply_profile_updates(
        current,
        {
            "skill_preferences_to_add": {
                "web_search": ["weather.com"],
                "text_to_image": ["anime style"],
            },
        },
    )
    assert updated.skill_preferences == {
        "web_search": ["accuweather.com", "weather.com"],
        "text_to_image": ["anime style"],
    }


def test_profile_update_skill_preferences_to_add_unknown_skill():
    current = UserProfile()
    updated = MemoryCore.apply_profile_updates(
        current,
        {"skill_preferences_to_add": {"new_skill": ["pref1"]}},
    )
    assert updated.skill_preferences == {"new_skill": ["pref1"]}


def test_profile_update_delta_keys_absent_from_to_dict():
    updated = MemoryCore.apply_profile_updates(
        UserProfile(),
        {"interests_to_add": ["x"], "facts_to_add": ["y"]},
    )
    d = updated.to_dict()
    assert "interests_to_add" not in d
    assert "facts_to_add" not in d
    assert "skill_preferences_to_add" not in d


def test_profile_update_mixed_delta_and_replace():
    current = UserProfile(interests=["A"])
    updated = MemoryCore.apply_profile_updates(
        current,
        {"interests_to_add": ["b"], "interests": ["Z"]},
    )
    assert updated.interests == ["Z"]


def test_profile_update_empty_delta_lists_noop():
    current = UserProfile(interests=["A"], facts=["B"])
    updated = MemoryCore.apply_profile_updates(
        current,
        {"interests_to_add": [], "facts_to_add": []},
    )
    assert updated.interests == ["A"]
    assert updated.facts == ["B"]


def test_profile_update_does_not_mutate_input():
    current = UserProfile(interests=["A"])
    original_interests = current.interests
    MemoryCore.apply_profile_updates(current, {"interests_to_add": ["B"]})
    assert current.interests is original_interests
    assert current.interests == ["A"]


@pytest.mark.asyncio
async def test_user_profile_legacy_load_without_skill_preferences():
    storage = FakeStorageApi()
    storage.data["user_profiles"] = {
        "1@1": json.dumps({
            "preferred_name": "Luke",
            "interests": ["Jedi"],
            "schema_version": 2,
        })
    }
    memory_provider = MemoryProvider(storage_api=storage)

    profile = await memory_provider.get_user_profile(user_id=1, chat_id=1)

    assert profile.skill_preferences == {}


@pytest.mark.asyncio
async def test_user_profile_replace_skill_preferences_roundtrip():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_user_profile(
        user_id=1,
        chat_id=1,
        user_profile={
            "skill_preferences": {"web_search": ["accuweather.com"]},
        },
    )

    stored = json.loads(storage.data["user_profiles"]["1@1"])
    assert stored["skill_preferences"] == {"web_search": ["accuweather.com"]}

    profile = await memory_provider.get_user_profile(user_id=1, chat_id=1)
    assert profile.skill_preferences == {"web_search": ["accuweather.com"]}


@pytest.mark.asyncio
async def test_user_profile_delta_only_sets_updated_on():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_user_profile(
        user_id=1,
        chat_id=1,
        user_profile={"facts_to_add": ["New fact"]},
    )

    stored = json.loads(storage.data["user_profiles"]["1@1"])
    assert stored["facts"] == ["New fact"]
    assert stored["updated_on"] != ""
    assert "facts_to_add" not in stored


@pytest.mark.asyncio
async def test_user_profile_delta_keys_not_persisted():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_user_profile(
        user_id=1,
        chat_id=1,
        user_profile={
            "interests_to_add": ["Python"],
            "skill_preferences_to_add": {"web_search": ["x.com"]},
        },
    )

    stored = json.loads(storage.data["user_profiles"]["1@1"])
    assert "interests_to_add" not in stored
    assert "skill_preferences_to_add" not in stored
    assert stored["interests"] == ["Python"]
    assert stored["skill_preferences"] == {"web_search": ["x.com"]}


@pytest.mark.asyncio
async def test_user_profile_scalar_replace_unchanged():
    storage = FakeStorageApi()
    memory_provider = MemoryProvider(storage_api=storage)

    await memory_provider.update_user_profile(
        user_id=1,
        chat_id=1,
        user_profile={"timezone": "Europe/Moscow"},
    )

    stored = json.loads(storage.data["user_profiles"]["1@1"])
    assert stored["timezone"] == "Europe/Moscow"


@pytest.mark.asyncio
async def test_conversation_stash_migrates_v1_content_field():
    storage = FakeStorageApi()
    storage.strings[CONVERSATION_STASH_REDIS_KEY] = json.dumps({
        "schema_version": 1,
        "conversations": {
            "9": {
                "chat_id": 9,
                "messages": [
                    {"role": "system", "content": "bootstrap"},
                    {"role": "user", "content": "legacy", "user_id": 7},
                ],
            },
        },
    })
    memory = MemoryProvider(storage_api=storage)
    await memory.restore_conversation_stash()
    assert CONVERSATION_STASH_REDIS_KEY not in storage.strings
    conv = memory.get_conversation(9)
    assert conv is not None
    assert conv.messages[0].kind == "prompt"
    assert conv.messages[1].text == "legacy"
    assert conv.messages[1].kind == "user"
    assert conv.visible_messages == 1
    assert conv.introduced_users == {7}
