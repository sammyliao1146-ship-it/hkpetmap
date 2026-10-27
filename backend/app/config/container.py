from dataclasses import dataclass, field
from pathlib import Path
import httpx
import ssl
import truststore
from agent.client_pool import close_all as close_model_clients
from backend.app.cache.redis_cache import RedisCache
from backend.app.config.llm_gate import LLMGate
from backend.app.data.featured import FeaturedStore
from backend.app.config.settings import Settings
from backend.app.services.pet_service import PetService
from backend.app.services.parking_service import ParkingService

@dataclass
class Container:
    settings: Settings
    cache: RedisCache
    client: httpx.AsyncClient
    pets: PetService
    llm_gate: LLMGate = field(init=False)
    featured: FeaturedStore = field(init=False)
    parking: ParkingService = field(init=False)

    def __post_init__(self):
        self.featured = FeaturedStore()
        self.parking = ParkingService(self.cache, self.client)
        s = self.settings
        self.llm_gate = LLMGate(s.llm_max_concurrency, s.llm_fallback_concurrency, s.llm_queue_timeout_seconds)

    async def aclose(self):
        await self.client.aclose()
        await close_model_clients()
        await self.cache.aclose()

async def build_container(settings: Settings, cache: RedisCache | None = None):
    cache = cache or RedisCache.from_url(settings.redis_url, settings.cache_prefix)
    client = httpx.AsyncClient(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=40, follow_redirects=True, trust_env=True, headers={'User-Agent':'HK-PetFinder/0.1 (public-data-reader)'})
    pets = PetService(cache, client, snapshot_path=Path(settings.snapshot_path) if settings.snapshot_path else None, max_age_seconds=settings.snapshot_max_age_seconds)
    await pets.load()
    return Container(settings, cache, client, pets)
