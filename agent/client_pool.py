"""Reusable AsyncOpenAI clients (keep-alive connections) held in a time-limited in-process cache.

Connection pools cannot be serialised to Redis, so they live in process memory and expire after
CLIENT_TTL_SECONDS without use; expired clients are closed.
"""
import asyncio
import hashlib
import time

from openai import AsyncOpenAI

CLIENT_TTL_SECONDS = 500
_pool: dict[tuple, list] = {}


def _key(api_key: str, base_url: str) -> tuple:
    return hashlib.sha256(api_key.encode()).hexdigest(), base_url


async def _close_quietly(client) -> None:
    try:
        await client.close()
    except Exception:  # best effort: the client may be bound to a finished loop
        pass


def get_client(api_key: str, base_url: str, timeout: float, *, ttl: float = CLIENT_TTL_SECONDS):
    """Return a client with this timeout sharing one pooled HTTP connection set.

    The result must NOT be closed by the caller: closing it would close the shared connections.
    """
    loop = asyncio.get_running_loop()
    now = time.monotonic()
    for key, (client, entry_loop, last_used) in list(_pool.items()):
        if now - last_used > ttl or entry_loop is not loop and entry_loop.is_closed():
            del _pool[key]
            if entry_loop is loop:
                loop.create_task(_close_quietly(client))
    key = _key(api_key, base_url)
    entry = _pool.get(key)
    if entry is None or entry[1] is not loop:
        entry = [AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0), loop, now]
        _pool[key] = entry
    entry[2] = now
    return entry[0].with_options(timeout=timeout)


async def close_all() -> None:
    clients = [entry[0] for entry in _pool.values()]
    _pool.clear()
    await asyncio.gather(*(_close_quietly(c) for c in clients))
