"""短期记忆 缓存5轮对话"""
from typing import Protocol

MEMORY_TTL_SECONDS = 600
MAX_MESSAGES = 5
MAX_CONTENT_CHARS = 8000


class JsonCache(Protocol):
    async def get_json(self, key: str): ...
    async def set_json(self, key: str, value, ttl:int | None = None) -> None: ...


class ConversationMemory:
    def __init__(self, cache: JsonCache, *, ttl: int = MEMORY_TTL_SECONDS, max_messages: int = MAX_MESSAGES) -> None:
        self.cache = cache
        self.ttl = ttl
        self.max_messages = max_messages

    @staticmethod
    def _key(session_id: str) -> str:
        return f"memory:{session_id}"

    async def load(self, session_id: str) -> list[dict[str, str]]:
        data = await self.cache.get_json(self._key(session_id))
        if not isinstance(data, list):
            return []
        return [{"role": m["role"], "content": m["content"]} for m in data
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
                ][-self.max_messages:]

    async def append(self, session_id: str, user: str, assistant: str) -> None:
        """Store one user/assistant exchange; each write refreshes the TTL."""
        messages = await self.load(session_id)
        messages += [{"role": "user", "content": user[:MAX_CONTENT_CHARS]},
                     {"role": "assistant", "content": assistant[:MAX_CONTENT_CHARS]}]
        await self.cache.set_json(self._key(session_id), messages[-self.max_messages:], self.ttl)
