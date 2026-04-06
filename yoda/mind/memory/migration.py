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


MIGRATIONS: dict[str, dict[int, MigrationStep]] = {
    "users": {1: _users_v1_to_v2},
    "user_profiles": {1: _user_profiles_v1_to_v2},
    "chats": {
        1: _chats_v1_to_v2,
        2: _chats_v2_to_v3,
    },
}


def migrate(entity: str, data: dict) -> dict:
    version = data.get("schema_version", 1)
    steps = MIGRATIONS.get(entity, {})
    while version in steps:
        data = steps[version](data)
        version += 1
    return data
