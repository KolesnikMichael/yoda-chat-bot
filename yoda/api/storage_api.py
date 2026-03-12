import asyncio
import redis


class StorageApi:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self._client = redis.StrictRedis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
        )

    async def hget(self, key: str, field: str) -> str | None:
        return await asyncio.to_thread(self._client.hget, key, field)

    async def hset(self, key: str, field: str, value: str) -> int:
        return await asyncio.to_thread(self._client.hset, key, field, value)
