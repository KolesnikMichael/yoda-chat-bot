import json

import pytest

from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.message import Message
from yoda.mind.memory.memory import (
    CONVERSATION_STASH_REDIS_KEY,
    MemoryCore,
    MemoryProvider,
)
from tests.test_memory_operation import FakeStorageApi


@pytest.mark.asyncio
async def test_private_chat_first_user_message_gets_introduction():
    storage = FakeStorageApi()
    storage.data["user_profiles"] = {
        "7@1": json.dumps({"preferred_name": "Luke", "schema_version": 2}),
    }
    memory = MemoryProvider(storage_api=storage)

    conversation, messages = await memory.append_conversation_line(
        conversation=None,
        chat_id=1,
        kind="user",
        role="user",
        line="hello",
        user_id=7,
    )

    assert conversation.messages[1].kind == "user_introduction"
    assert conversation.messages[2].kind == "user"
    assert conversation.visible_messages == 1
    assert conversation.introduced_users == {7}
    assert any("Preferred name: Luke" in m["content"] for m in messages)


@pytest.mark.asyncio
async def test_private_chat_second_user_message_unchanged():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    conversation, _ = await memory.append_conversation_line(
        conversation=None,
        chat_id=1,
        kind="user",
        role="user",
        line="first",
        user_id=7,
    )
    before = len(conversation.messages)

    conversation, _ = await memory.append_conversation_line(
        conversation=conversation,
        chat_id=1,
        kind="user",
        role="user",
        line="second",
        user_id=7,
    )

    assert len(conversation.messages) == before + 1
    assert sum(1 for m in conversation.messages if m.kind == "user_introduction") == 1
    assert conversation.visible_messages == 2


@pytest.mark.asyncio
async def test_group_chat_two_users_in_speak_order():
    storage = FakeStorageApi()
    storage.data["user_profiles"] = {
        "1@99": json.dumps({"preferred_name": "Luke", "schema_version": 2}),
        "2@99": json.dumps({"preferred_name": "Leia", "schema_version": 2}),
    }
    memory = MemoryProvider(storage_api=storage)
    conversation = None

    conversation, _ = await memory.append_conversation_line(
        conversation=conversation,
        chat_id=99,
        kind="user",
        role="user",
        line="from luke",
        user_id=1,
    )
    conversation, _ = await memory.append_conversation_line(
        conversation=conversation,
        chat_id=99,
        kind="user",
        role="user",
        line="from leia",
        user_id=2,
    )

    kinds = [m.kind for m in conversation.messages]
    assert kinds.count("user_introduction") == 2
    assert kinds.index("user_introduction") < kinds.index("user")
    assert conversation.introduced_users == {1, 2}
    assert conversation.visible_messages == 2


@pytest.mark.asyncio
async def test_migrated_v2_stash_restore_includes_introductions_in_llm_list():
    storage = FakeStorageApi()
    storage.data["user_profiles"] = {
        "7@1": json.dumps({"preferred_name": "Luke", "schema_version": 2}),
    }
    storage.strings[CONVERSATION_STASH_REDIS_KEY] = json.dumps({
        "schema_version": 2,
        "conversations": {
            "1": {
                "chat_id": 1,
                "messages": [
                    {"role": "system", "text": "bootstrap", "user_id": None},
                    {
                        "role": "system",
                        "text": 'On 2026-03-09 Luke sent: "hi"',
                        "user_id": 7,
                    },
                ],
            },
        },
    })
    memory = MemoryProvider(storage_api=storage)
    await memory.restore_conversation_stash()

    conv = memory.get_conversation(1)
    assert conv is not None
    llm = conv.to_llm_messages()
    assert any("Preferred name: Luke" in m["content"] for m in llm)
    assert conv.visible_messages == 1


@pytest.mark.asyncio
async def test_visible_messages_counts_user_and_assistant_only():
    storage = FakeStorageApi()
    memory = MemoryProvider(storage_api=storage)
    conversation, _ = await memory.append_conversation_line(
        conversation=None,
        chat_id=1,
        kind="user",
        role="user",
        line="hi",
        user_id=7,
    )
    conversation, _ = MemoryCore.add_conversation_line(
        conversation=conversation,
        chat_id=1,
        kind="assistant",
        role="assistant",
        line="yo",
    )

    assert conversation.visible_messages == 2
    assert len(conversation.messages) > 3
