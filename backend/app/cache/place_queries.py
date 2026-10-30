"""Bounded per-process L1 plus shared Redis results for public saved-place queries."""
import asyncio
import hashlib
import json
import logging

from backend.app.cache.redis_cache import MemoryCache
from backend.app.cache.singleflight import SingleFlight
from backend.app.data.geography import DISTRICTS, REGION_ALIASES

logger = logging.getLogger(__name__)
QUERY_TTL = 600
QUERY_CACHE_VERSION = 'place-query:v1'


def canonical_district(value):
    value = ' '.join(value.casefold().strip().split()).removesuffix(' district')
    if value in {'hong kong', 'all hong kong', '全港', '香港', 'any'}:
        return ''
    value = value.removesuffix('區') or value
    return REGION_ALIASES.get(value, DISTRICTS.get(value, value))


class PlaceQueryCache:
    def __init__(self, shared):
        self.shared = shared
        self.local = MemoryCache(max_entries=512, max_bytes=8 * 1024 * 1024)
        self.flights = SingleFlight()

    @staticmethod
    def key(revision, parameters):
        encoded = json.dumps([revision, parameters], sort_keys=True, ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode()
        return QUERY_CACHE_VERSION + ':' + hashlib.sha256(encoded).hexdigest()

    async def get_or_create(self, revision, parameters, factory):
        key = self.key(revision, parameters)
        raw = await self.local.get(key)
        if raw is not None:
            return json.loads(raw)

        async def fill():
            # Coalesced waiters share computation, never mutable Python results.
            raw = await self.local.get(key)
            if raw is not None:
                return raw
            value = None
            try:
                async with asyncio.timeout(.1):
                    value = await self.shared.get_json(key)
            except (TimeoutError, OSError, ValueError, TypeError):
                logger.warning('place_query_cache_read_unavailable')
            if not isinstance(value, dict) or not isinstance(value.get('items'), list):
                value = factory()
                try:
                    async with asyncio.timeout(.1):
                        await self.shared.set_json(key, value, QUERY_TTL)
                except (TimeoutError, OSError, ValueError, TypeError):
                    logger.warning('place_query_cache_write_unavailable')
            raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
            await self.local.set(key, raw, QUERY_TTL)
            return raw

        return json.loads(await self.flights.run(key, fill))

    async def aclose(self):
        await self.flights.aclose()
        await self.local.aclose()
