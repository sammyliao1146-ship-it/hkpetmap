import asyncio
import os
from uuid import uuid4

import pytest

from backend.app.cache.redis_cache import RedisCache


class StalledRedis:
    def __init__(self):self.attempts=0
    async def get(self,*args):await asyncio.sleep(5)
    async def set(self,*args,**kwargs):await asyncio.sleep(5)
    async def eval(self,*args):
        self.attempts+=1
        await asyncio.sleep(5)
    async def aclose(self):pass


def test_nearby_and_memory_cache_fall_back_before_the_response_deadline():
    async def run():
        cache=RedisCache(StalledRedis(),'latency')
        for key in ('nearby:v2:test','memory:session_test'):
            await asyncio.wait_for(cache.set_json(key,{'saved':True},60),.3)
            assert await asyncio.wait_for(cache.get_json(key),.3)=={'saved':True}
        await cache.aclose()
    asyncio.run(run())


def test_rate_limit_outage_is_bounded_and_does_not_retry_every_request():
    async def run():
        client=StalledRedis();cache=RedisCache(client,'latency')
        assert await asyncio.wait_for(cache.hit('rate:test',60),.3)==1
        for expected in range(2,10):
            assert await asyncio.wait_for(cache.hit('rate:test',60),.1)==expected
        assert client.attempts==1
        # After cooldown, a recovered server is tried rather than disabled forever.
        cache._rate_retry_at=0
        async def recovered(*args):return 10
        client.eval=recovered
        assert await cache.hit('rate:test',60)==10
        await cache.aclose()
    asyncio.run(run())


def test_required_snapshot_publication_is_not_silently_downgraded():
    async def run():
        cache=RedisCache(None)
        with pytest.raises(RuntimeError):
            await cache.publish_snapshot({},'v1',60,require_shared=True)
        await cache.aclose()
    asyncio.run(run())


def test_ui_http_answer_survives_stalled_redis_without_calling_a_model(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import HttpUrl
    from main import app
    from test_pet_data import service
    from backend.app.config.settings import Settings
    from backend.app.config.container import Container
    svc,old_cache,client=service(tmp_path)
    cache=RedisCache(StalledRedis(),'http-latency');svc.cache=cache
    p=svc.snapshot.places[1];p.district='九龍城區';p.cuisines=['咖啡／輕食'];p.cuisine_source=HttpUrl('https://example.org/menu')
    c=Container(Settings(api_key='not-used',model='not-used',base_url='https://example.invalid',cors_origins=[]),cache,client,svc)
    async def reject_model(*args,**kwargs):raise AssertionError('Saved UI question called a model')
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent',reject_model)
    app.state.container=c
    try:
        import time
        with TestClient(app) as api:
            started=time.perf_counter()
            response=api.post('/api/v1/assistant/chat',json={'message':'我想帶狗去九龍城飲咖啡，幫我搵有資料來源嘅餐廳。','language':'zh-Hant','session_id':'slow_redis_session'})
            assert time.perf_counter()-started<1
            assert response.status_code==200
            assert response.json()['model']=='saved-data' and response.json()['sources']
    finally:del app.state.container


@pytest.mark.skipif(not os.getenv('PET_TEST_REDIS_URL'),reason='Dedicated test Redis not supplied')
def test_real_redis_rate_counter_is_atomic_and_expiry_does_not_slide():
    async def run():
        cache=RedisCache.from_url(os.environ['PET_TEST_REDIS_URL'],'latency_'+uuid4().hex)
        try:
            assert await cache.hit('rate:test',2)==1
            assert await cache.client.ttl(cache._key('rate:test'))>0
            await asyncio.sleep(1.05)
            assert await cache.hit('rate:test',2)==2
            assert await cache.client.ttl(cache._key('rate:test'))<=1
            await asyncio.sleep(1.05)
            assert await cache.hit('rate:test',2)==1
            assert not cache._warned  # Passing through memory would not test Lua/expiry.
        finally:await cache.aclose()
    asyncio.run(run())
