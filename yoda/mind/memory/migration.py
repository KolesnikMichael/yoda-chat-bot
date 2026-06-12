from collections.abc import Callable

MigrationStep = Callable[[dict], dict]


class MigrationError(Exception):
    def __init__(self, *, chat_id: int, message_index: int, text_prefix: str) -> None:
        self.chat_id = chat_id
        self.message_index = message_index
        self.text_prefix = text_prefix
        super().__init__(
            f"conversation stash migration failed for chat {chat_id} "
            f"at message index {message_index}: unknown system prefix "
            f"{text_prefix!r}"
        )


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


def _conversation_stash_v2_to_v3(data: dict) -> dict:
    from .memory import MemoryCore

    conversations = data.get("conversations", {})
    for cid, payload in conversations.items():
        if not isinstance(payload, dict):
            continue
        chat_id = int(payload.get("chat_id", cid))
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            continue

        introduced_users: set[int] = set()
        visible_messages = 0
        last_visible_at = 0.0

        for index, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            kind = MemoryCore.infer_kind(
                msg,
                is_first=(index == 0),
                chat_id=chat_id,
                message_index=index,
            )
            msg["kind"] = kind
            if kind in ("user", "assistant"):
                visible_messages += 1
                last_visible_at = max(
                    last_visible_at,
                    MemoryCore.parse_message_timestamp(msg.get("timestamp", "")),
                )
            user_id = msg.get("user_id")
            if kind == "user" and user_id is not None:
                introduced_users.add(int(user_id))

        payload["introduced_users"] = sorted(introduced_users)
        payload["visible_messages"] = visible_messages
        payload["last_visible_at"] = last_visible_at
        payload["last_compressed_at"] = 0.0
        payload["pending_vectorization"] = []

    data["schema_version"] = 3
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
        2: _conversation_stash_v2_to_v3,
    },
}


def migrate(entity: str, data: dict) -> dict:
    version = data.get("schema_version", 1)
    steps = MIGRATIONS.get(entity, {})
    while version in steps:
        data = steps[version](data)
        version += 1
    return data
