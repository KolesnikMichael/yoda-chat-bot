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
            decode_responses=True
        )


    def refresh_user_info(self, user_id: int, user_info: dict):
        current_user_info = self.redis_client.hget("users", user_id)
        if current_user_info:
            current_user_info = json.loads(current_user_info)
        else:
            current_user_info = {"known_since": user_info.get("last_active")}
            logger.info(f"Registered user {user_id}")
        self.redis_client.hset("users", user_id, json.dumps({**current_user_info, **user_info}))
  

    def refresh_user_profile(self, user_id: int, chat_id: int, user_profile: dict):
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
        self.redis_client.hset("user_profiles", user_profile_id, json.dumps({**current_user_profile, **user_profile}))
