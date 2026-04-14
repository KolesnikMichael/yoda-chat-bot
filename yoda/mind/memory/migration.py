from collections.abc import Callable

MigrationStep = Callable[[dict], dict]


def _users_v1_to_v2(data: dict) -> dict:
    data.pop("language_code", None)
    data["schema_version"] = 2
    return data


def _user_profiles_v1_to_v2(data: dict) -> dict:
    if "nickname" in data:
        data["preferred_name"] = data.pop("nickname")
    if "miscellaneous" in data:
        data["facts"] = data.pop("miscellaneous")
    for field in ("preferred_language", "education", "birthday", "age"):
        data.pop(field, None)
    data["schema_version"] = 2
    return data


def _chats_v1_to_v2(data: dict) -> dict:
    data.setdefault("chat_type", "")
    data.setdefault("history", [])
    data.setdefault("conversation", {"users": [], "messages": []})
    data["schema_version"] = 2
    return data


def _chats_v2_to_v3(data: dict) -> dict:
    conversation = data.pop("conversation", {})
    data["users"] = conversation.get("users", [])
    data.setdefault("updated_on", "")
    data["schema_version"] = 3
    return data


def _chats_v3_to_v4(data: dict) -> dict:
    data.pop("users", None)
    data["schema_version"] = 4
    return data


def _conversation_stash_v1_to_v2(data: dict) -> dict:
    """Normalize legacy message dicts (e.g. content instead of text)."""
    conversations = data.get("conversations", {})
    for _cid, payload in conversations.items():
        if not isinstance(payload, dict):
            continue
        for msg in payload.get("messages", []):
            if not isinstance(msg, dict):
                continue
            if "text" not in msg and "content" in msg:
                msg["text"] = msg.pop("content")
            msg.setdefault("media_type", "text")
            msg.setdefault("timestamp", "")
            msg.setdefault("message_id", None)
            msg.setdefault("user_id", None)
    data["schema_version"] = 2
    return data


MIGRATIONS: dict[str, dict[int, MigrationStep]] = {
    "users": {1: _users_v1_to_v2},
    "user_profiles": {1: _user_profiles_v1_to_v2},
    "chats": {
        1: _chats_v1_to_v2,
        2: _chats_v2_to_v3,
        3: _chats_v3_to_v4,
    },
    "conversation_stash": {
        1: _conversation_stash_v1_to_v2,
    },
}


def migrate(entity: str, data: dict) -> dict:
    version = data.get("schema_version", 1)
    steps = MIGRATIONS.get(entity, {})
    while version in steps:
        data = steps[version](data)
        version += 1
    return data
