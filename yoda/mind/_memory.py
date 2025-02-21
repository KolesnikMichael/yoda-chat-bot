import datetime
import logging
import redis
import json

logger = logging.getLogger(__name__)

class Memory:
    def __init__(self, mind, settings):
        self.settings = settings
        self.mind = mind
        self.redis_client = redis.StrictRedis(
            host = settings.get("redis_host", "localhost"),
            port = settings.get("redis_port", 6379),
            db = settings.get("redis_db", 0),
            decode_responses = True
        )


    def update_sender_info(self, user_id: int, chat_id: int, user_info: dict):
        current_user_info = self.redis_client.hget("users", user_id)

        if current_user_info:
            current_user_info = json.loads(current_user_info)
        else:
            current_user_info = {"known_since": user_info.get("last_active")}
            logger.info(f"Registered user {user_id}")

        self.redis_client.hset("users", user_id, json.dumps({**current_user_info, **user_info}))

        chat_type = 'private' if user_id == chat_id else 'group'
        self.update_chat_info(chat_id=chat_id, chat_type=chat_type, last_active=user_info.get("last_active"))


    def update_chat_info(self, chat_id: int, chat_type: str, last_active: str):
        SCHEMA_VERSION = 2
        current_chat_info = self.redis_client.hget("chats", chat_id)

        if current_chat_info:
            current_chat_info = json.loads(current_chat_info)
            current_schema_version = current_chat_info.get("schema_version")

            if current_schema_version < SCHEMA_VERSION:
                for version in range(current_schema_version, SCHEMA_VERSION):
                    match version:
                        case 1:
                            delta = {
                                "chat_type": chat_type,
                                "history": [],
                                "conversation": {
                                    "users": [],
                                    "messages": []
                                },
                                "schema_version": version + 1
                                }
                            current_chat_info = {**current_chat_info, **delta}

        else:
            current_chat_info = {
                "chat_type": chat_type,
                "history": [],
                "conversation": {
                    "users": [],
                    "messages": []
                },
                "last_active": "",
                "schema_version": SCHEMA_VERSION
                }
            logger.info(f"Registered chat {chat_id}")

        current_chat_info["last_active"] = last_active
        self.redis_client.hset("chats", chat_id, json.dumps(current_chat_info))
  

    def update_user_profile(self, user_id: int, chat_id: int, user_profile: dict):
        user_profile_id = f"{user_id}@{chat_id}"
        current_user_profile = self.redis_client.hget("users", user_profile_id)
        if current_user_profile:
            current_user_profile = json.loads(current_user_profile)
        else:
            current_user_profile = {
                "nickname": "",
                "preferred_language": "",
                "gender": "",
                "birthday": "",
                "age": "",
                "location": "",
                "timezone": "",
                "education": "",
                "occupation": "",
                "interests": [""],
                "miscellaneous": [""],
                "schema_version": 1
                }
        current_user_profile = {**current_user_profile, **user_profile}
        current_user_profile["updated_on"] = f"{datetime.utcfromtimestamp()}"
        self.redis_client.hset("user_profiles", user_profile_id, json.dumps(current_user_profile))

