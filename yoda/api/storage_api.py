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

    async def hdel(self, key: str, field: str) -> int:
        return await asyncio.to_thread(self._client.hdel, key, field)

    async def keys(self, pattern: str) -> list[str]:
        return await asyncio.to_thread(self._client.keys, pattern)

    async def hgetall(self, key: str) -> dict[str, str]:
        return await asyncio.to_thread(self._client.hgetall, key)

    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(self._client.get, key)

    async def set(self, key: str, value: str) -> bool | None:
        return await asyncio.to_thread(self._client.set, key, value)

    async def delete(self, key: str) -> int:
        return await asyncio.to_thread(self._client.delete, key)
