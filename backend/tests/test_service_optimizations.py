import asyncio
from types import SimpleNamespace as NS
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from agent.assembly.tool_policy import tool_names
from agent.data.data_access import PetDataAccess
from agent.data.saved_lookup import saved_lookup
from backend.app.cache.singleflight import SingleFlight
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from backend.app.models.assistant import ChatOrigin, ChatResponse
from backend.app.observability.store import ConversationStore
from backend.app.observability.trace import TurnTrace
from backend.app.routers.assistant import _nearby_featured, _traced_turn
from backend.app.services.photo_service import prepare_variants, photo_response, variant_path
from main import app
from test_pet_data import service


def test_nearby_hits_skip_serializing_and_overlapping_misses_share_work(tmp_path):
    async def run():
        svc, cache, client = service(tmp_path)
        class Featured:
            version = ''
            builds = 0
            def ensure(self, items, version):
                self.builds += 1; self.version = version
            def nearest(self, *args):
                return []
        featured = Featured()
        c = NS(pets=svc, cache=cache, featured=featured, nearby_flights=SingleFlight())
        origin = ChatOrigin(latitude=22.3, longitude=114.17)
        with patch.object(svc, 'places', wraps=svc.places) as dump:
            await asyncio.gather(*(_nearby_featured(c, origin, 'en') for _ in range(8)))
            assert dump.call_count == 1 and featured.builds == 1
            await _nearby_featured(c, origin, 'en')
            assert dump.call_count == 1
            # Changed enrichment invalidates despite an unchanged fetched_at.
            svc.snapshot = svc.snapshot.model_copy(deep=True)
            svc.snapshot.places[1].telephone = '12345678'
            await _nearby_featured(c, origin, 'en')
            assert dump.call_count == 2
        await c.nearby_flights.aclose(); await client.aclose(); await cache.aclose()
    asyncio.run(run())


def test_coalesced_read_survives_one_waiter_cancelling():
    async def run():
        flight = SingleFlight(); ready = asyncio.Event(); started = asyncio.Event(); calls = 0
        async def read():
            nonlocal calls
            calls += 1; started.set(); await ready.wait(); return 42
        a = asyncio.create_task(flight.run('same', read)); await started.wait()
        b = asyncio.create_task(flight.run('same', read)); await asyncio.sleep(0)
        a.cancel()
        try: await a
        except asyncio.CancelledError: pass
        ready.set(); assert await b == 42 and calls == 1
        await asyncio.sleep(0); assert not flight.pending
    asyncio.run(run())


def test_nearby_answer_with_nonempty_sources_can_be_saved_in_json_cache(tmp_path):
    async def run():
        svc,cache,client=service(tmp_path)
        p=svc.snapshot.places[1]
        row={'id':p.id,'name':p.name,'name_en':'Sample Restaurant','address':'Sample Road',
             'rating':4.5,'rating_count':25,'price_min':100,'price_max':180,'distance_m':100,'cuisine':'日式'}
        featured=NS(version=svc.data_revision(),nearest=lambda *args:[row])
        c=NS(pets=svc,cache=cache,featured=featured,nearby_flights=SingleFlight())
        value=await _nearby_featured(c,ChatOrigin(latitude=22.3,longitude=114.17),'en')
        assert value['sources'][0]['url']==str(p.source_url)
        key=f'nearby:v2:{svc.data_revision()}:en:22.300:114.170'
        assert (await cache.get_json(key))['sources']==value['sources']
        await c.nearby_flights.aclose();await client.aclose();await cache.aclose()
    asyncio.run(run())


def test_initial_storage_does_not_delay_model_and_final_save_is_joined():
    async def run():
        release = asyncio.Event(); snapshots = []
        class Store:
            async def save(self, trace):
                await release.wait(); snapshots.append(trace.status)
        trace = TurnTrace('session_1', 'question', 'en')
        async def answer(*args):
            # This could not execute if the initial DB save were awaited first.
            release.set(); return ChatResponse(answer='Answer', model='test')
        with patch('backend.app.routers.assistant._handle', answer):
            result = await asyncio.wait_for(_traced_turn(NS(language='en'), NS(), NS(conversations=Store()), trace), 1)
        assert result.answer == 'Answer' and len(snapshots) == 2 and snapshots[-1] == 'success'
    asyncio.run(run())


def test_storage_retries_once_and_retention_is_disabled_by_default():
    async def run():
        class Pool:
            calls = 0
            async def execute(self, *args):
                self.calls += 1
                if self.calls == 1: raise OSError('unavailable')
        store = ConversationStore('local-only'); store.pool = Pool()
        trace = TurnTrace('session_1', 'test', 'en')
        await store.save(trace)
        assert trace.storage_status == 'saved' and store.pool.calls == 2
        assert await store.prune() == {'enabled':False, 'deleted':0}
    asyncio.run(run())


def test_tools_and_saved_lookups_do_not_guess_ambiguous_places(tmp_path):
    svc, _, _ = service(tmp_path)
    svc.snapshot.places[1].name_en = 'Cafe One'; svc.snapshot.places[1].telephone = '12345678'
    access = PetDataAccess(svc)
    value = saved_lookup('phone for Cafe One', [], access, 'en')
    assert '12345678' in value['answer'] and value['places'][0]['id'] == 'restaurant:1'
    assert saved_lookup('phone for it', [], access, 'en') is None
    assert saved_lookup('phone for Cafe One and book a table', [], access, 'en') is None
    assert saved_lookup('latest phone for Cafe One', [], access, 'en') is None
    history = [{'role':'assistant', 'content':'Cafe One'}]
    assert saved_lookup('phone for it', history, access, 'en')
    assert 'get_pet_directions' not in tool_names('map_query')
    assert 'get_pet_transport' in tool_names('transport')
    assert 'search_pet_web_knowledge' in tool_names('pet_policy')
    assert 'search_pet_activities' not in tool_names('transport')


def test_prepared_photos_bypass_resize_and_change_with_content(tmp_path):
    path = tmp_path/'source.jpg'; Image.new('RGB', (1000,800), 'red').save(path)
    assert prepare_variants(path) == 2
    assert prepare_variants(path) == 0
    old = variant_path(path, 'thumb')
    with patch('backend.app.services.photo_service.Image.open', side_effect=AssertionError('must not resize')):
        assert photo_response(path, 'thumb').path == old
    Image.new('RGB', (1000,800), 'blue').save(path)
    assert variant_path(path, 'thumb') != old
    assert prepare_variants(path) == 2


def test_admin_data_requires_auth_and_shell_contains_no_user_data(tmp_path):
    svc, cache, client = service(tmp_path)
    c = Container(Settings(api_key='test', model='test', base_url='https://example.invalid', cors_origins=[], trace_admin_token='test-private'), cache, client, svc)
    class Store:
        async def stats(self, days): return {'turns':2, 'days':days}
        async def recent(self, limit, before): return []
        async def get(self, trace_id): return {'question':'private question'}
        async def aclose(self): pass
    c.conversations = Store(); app.state.container = c
    try:
        with TestClient(app) as api:
            shell = api.get('/api/v1/assistant/admin')
            assert shell.status_code == 200 and 'private question' not in shell.text
            assert 'test-private' not in shell.text and 'nonce-' in shell.headers['content-security-policy']
            for path in ('stats', 'turns', 'trace/trace_test'):
                assert api.get('/api/v1/assistant/admin/'+path).status_code == 401
                response = api.get('/api/v1/assistant/admin/'+path, headers={'Authorization':'Bearer test-private'})
                assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
    finally: del app.state.container
