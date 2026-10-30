"""Async cache backed by Redis, with an in-process fallback when Redis is unreachable."""
import asyncio
from collections import OrderedDict
import json
import logging
import time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
HIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


class MemoryCache:
    """Bounded LRU fallback with periodic expiry, including while the cache is idle."""

    def __init__(self, *, max_entries: int = 2048, max_bytes: int = 64*1024*1024,
                 cleanup_interval: float = 30) -> None:
        if max_entries < 1 or max_bytes < 1 or cleanup_interval <= 0:
            raise ValueError('Cache capacity and cleanup interval must be positive')
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.cleanup_interval = cleanup_interval
        self._data: OrderedDict[str, tuple[float | None, bytes]] = OrderedDict()
        self._bytes = 0
        self._cleanup_handle: asyncio.TimerHandle | None = None
        self._cleanup_loop: asyncio.AbstractEventLoop | None = None

    def _drop(self, key: str) -> None:
        entry = self._data.pop(key, None)
        if entry is not None:
            self._bytes -= len(key.encode('utf-8')) + len(entry[1])

    def _expire(self) -> None:
        now = time.monotonic()
        for key, (expires, _) in list(self._data.items()):
            if expires is not None and expires <= now:
                self._drop(key)

    def _ensure_cleanup(self) -> None:
        loop = asyncio.get_running_loop()
        if self._cleanup_handle is not None and self._cleanup_loop is not loop:
            self._cleanup_handle.cancel()
            self._cleanup_handle = None
        if self._data and self._cleanup_handle is None:
            self._cleanup_loop = loop
            self._cleanup_handle = loop.call_later(self.cleanup_interval, self._sweep)

    def _sweep(self) -> None:
        self._cleanup_handle = None
        self._expire()
        self._ensure_cleanup()

    def _store(self, key: str, value: bytes, expires: float | None) -> None:
        self._expire()
        self._drop(key)
        size = len(key.encode('utf-8')) + len(value)
        if size > self.max_bytes or (expires is not None and expires <= time.monotonic()):
            return
        while self._data and (len(self._data) >= self.max_entries or self._bytes + size > self.max_bytes):
            self._drop(next(iter(self._data)))
        self._data[key] = (expires, value)
        self._bytes += size
        self._ensure_cleanup()

    async def get(self, key: str) -> bytes | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires is not None and expires <= time.monotonic():
            self._drop(key)
            return None
        self._data.move_to_end(key)
        self._ensure_cleanup()
        return value

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self._store(key, value, time.monotonic() + ttl if ttl is not None else None)

    async def set_if_absent(self, key: str, ttl: int) -> bool:
        if await self.get(key) is not None:
            return False
        await self.set(key, b"1", ttl)
        return True

    async def incr_window(self, key: str, window: int) -> int:
        current = await self.get(key)
        count = int(current or 0) + 1
        entry = self._data.get(key)
        expires = entry[0] if entry and current is not None else time.monotonic() + window
        self._store(key, str(count).encode(), expires)
        return count

    async def aclose(self) -> None:
        if self._cleanup_handle is not None:
            self._cleanup_handle.cancel()
            self._cleanup_handle = None
        self._cleanup_loop = None
        self._data.clear()
        self._bytes = 0


class RedisCache:
    """Namespaced JSON/bytes cache. A Redis outage degrades to memory instead of failing requests."""

    def __init__(self, client: Redis | None, prefix: str = "hkpet") -> None:
        self.client = client
        self.prefix = prefix
        self.fallback = MemoryCache()
        self._warned = False
        self._rate_retry_at = 0.0

    @classmethod
    def from_url(cls, url: str, prefix: str = "hkpet") -> "RedisCache":
        return cls(Redis.from_url(url, socket_connect_timeout=2, socket_timeout=5), prefix)

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _degraded(self, exc: Exception) -> None:
        if not self._warned:
            logger.warning("Redis unavailable, using in-process cache: %s", type(exc).__name__)
            self._warned = True

    async def ping(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(await self.client.ping())
        except (RedisError, OSError):
            return False

    async def get_bytes(self, key: str) -> bytes | None:
        if self.client is not None:
            try:
                timeout=.05 if key.startswith('memory:') else .1 if key.startswith('nearby:') else None
                async with asyncio.timeout(timeout):
                    return await self.client.get(self._key(key))
            except (RedisError, OSError) as exc:
                self._degraded(exc)
        return await self.fallback.get(self._key(key))

    async def set_bytes(self, key: str, value: bytes, ttl: int | None = None) -> None:
        if self.client is not None:
            try:
                timeout=.05 if key.startswith('memory:') else .1 if key.startswith('nearby:') else None
                async with asyncio.timeout(timeout):
                    await self.client.set(self._key(key), value, ex=ttl)
                return
            except (RedisError, OSError) as exc:
                self._degraded(exc)
        await self.fallback.set(self._key(key), value, ttl)

    async def get_json(self, key: str) -> Any | None:
        raw = await self.get_bytes(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.set_bytes(key, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(), ttl)

    async def publish_snapshot(self,value:Any,revision:str,ttl:int,*,require_shared=False):
        """Publish the payload and its reader revision in one Redis transaction."""
        payload=json.dumps(value,ensure_ascii=False,separators=(",", ":")).encode()
        if self.client is not None:
            try:
                async with self.client.pipeline(transaction=True) as pipe:
                    pipe.set(self._key('snapshot:v1'),payload,ex=ttl)
                    pipe.set(self._key('snapshot:revision'),revision.encode(),ex=ttl)
                    await pipe.execute()
                return
            except (RedisError,OSError) as exc:
                if require_shared:raise
                self._degraded(exc)
        elif require_shared:
            raise RuntimeError('Shared snapshot publication requires Redis')
        await self.fallback.set(self._key('snapshot:v1'),payload,ttl)
        await self.fallback.set(self._key('snapshot:revision'),revision.encode(),ttl)

    async def set_if_absent(self, key: str, ttl: int) -> bool:
        """True when the caller won the right to act; used to throttle upstream retries."""
        if self.client is not None:
            try:
                return bool(await self.client.set(self._key(key), b"1", ex=ttl, nx=True))
            except (RedisError, OSError) as exc:
                self._degraded(exc)
        return await self.fallback.set_if_absent(self._key(key), ttl)

    async def hit(self, key: str, window: int) -> int:
        """Fixed-window counter, returns the number of hits in the current window."""
        if self.client is not None and time.monotonic() >= self._rate_retry_at:
            try:
                # Atomic increment + initial expiry: a cancellation cannot leave an immortal key.
                async with asyncio.timeout(.1):
                    count = await self.client.eval(HIT_SCRIPT, 1, self._key(key), window)
                return int(count)
            except (RedisError, OSError) as exc:
                self._rate_retry_at = time.monotonic()+30
                self._degraded(exc)
        return await self.fallback.incr_window(self._key(key), window)

    async def aclose(self) -> None:
        if self.client is not None:
            try:
                await self.client.aclose()
            except (RedisError, OSError):
                pass
        await self.fallback.aclose()
