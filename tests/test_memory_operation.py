import json

import pytest

from yoda.mind.affect import AffectCore
from yoda.mind.cognition import CognitionCore
from yoda.mind.memory.data.system_prompt import DEFAULT_SYSTEM_PROMPT
from yoda.mind.memory.memory import MemoryCore, MemoryProvider
from yoda.mind.memory.migration import migrate


class FakeStorageApi:
    def __init__(self):
        self.data = {}

    async def hget(self, key: str, field: str):
        return self.data.get(key, {}).get(field)

    async def hset(self, key: str, field: str, value: str):
        bucket = self.data.setdefault(key, {})
        bucket[field] = value
        return 1


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
        role="user",
        line="Hello there",
        system_prompt="Reply as Yoda from Star Wars",
    )

    assert messages[0] == {"role": "system",
                           "content": "Reply as Yoda from Star Wars"}
    assert messages[1] == {"role": "user", "content": "Hello there"}


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
