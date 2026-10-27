import asyncio
from types import SimpleNamespace

from backend.app.cache.redis_cache import MemoryCache


def test_idle_cleanup_collects_1000_expired_unique_keys_without_reading_them(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr('backend.app.cache.redis_cache.time',SimpleNamespace(monotonic=lambda:clock[0]))

    async def run():
        cache=MemoryCache(cleanup_interval=.01)
        for i in range(1000):
            await cache.set(f'session:{i}',b'value',ttl=60)
        assert len(cache._data)==1000
        clock[0]+=61
        await asyncio.sleep(.04)
        assert len(cache._data)==0 and cache._bytes==0
        assert cache._cleanup_handle is None
        await cache.aclose()
    asyncio.run(run())


def test_entry_capacity_evicts_least_recently_used_and_shutdown_cancels_cleanup():
    async def run():
        cache=MemoryCache(max_entries=3)
        for key in ['a','b','c']:await cache.set(key,b'value')
        assert await cache.get('a')==b'value'
        await cache.set('d',b'value')
        assert await cache.get('b') is None
        assert len(cache._data)==3
        for i in range(1000):await cache.set(f'location:{i}',b'point')
        assert len(cache._data)==3
        handle=cache._cleanup_handle
        await cache.aclose()
        assert handle.cancelled() and not cache._data and cache._bytes==0
    asyncio.run(run())


def test_byte_capacity_and_oversized_replacement_do_not_return_stale_value():
    async def run():
        cache=MemoryCache(max_bytes=8)
        await cache.set('a',b'123');await cache.set('b',b'456')
        assert cache._bytes==8
        await cache.get('a');await cache.set('c',b'789')
        assert await cache.get('b') is None
        assert await cache.get('a')==b'123' and cache._bytes<=8
        await cache.set('a',b'x'*9)
        assert await cache.get('a') is None and cache._bytes==4
        await cache.aclose()
    asyncio.run(run())


def test_global_expiry_precedes_capacity_eviction_and_fixed_window_does_not_slide(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr('backend.app.cache.redis_cache.time',SimpleNamespace(monotonic=lambda:clock[0]))

    async def run():
        cache=MemoryCache(max_entries=2)
        await cache.set('live',b'value',ttl=100)
        await cache.set('expired',b'value',ttl=1)
        clock[0]+=2
        await cache.set('new',b'value',ttl=100)
        assert await cache.get('live')==b'value' and await cache.get('expired') is None
        await cache.aclose()
        cache=MemoryCache()
        assert await cache.incr_window('rate',10)==1
        clock[0]+=9
        assert await cache.incr_window('rate',10)==2
        clock[0]+=2
        assert await cache.incr_window('rate',10)==1
        assert await cache.set_if_absent('retry',5)
        assert not await cache.set_if_absent('retry',5)
        clock[0]+=6
        assert await cache.set_if_absent('retry',5)
        await cache.aclose()
    asyncio.run(run())
