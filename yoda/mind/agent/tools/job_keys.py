ACTIVE_JOBS_KEY_PREFIX = "active_jobs"


def active_jobs_key(chat_id: int) -> str:
    return f"{ACTIVE_JOBS_KEY_PREFIX}:{chat_id}"
