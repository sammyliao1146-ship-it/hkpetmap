import asyncio
import re
from unittest.mock import patch

import pytest

from agent.data.data_access import PetDataAccess
from agent.data.fast_answers import fast_answer
from backend.app.cache.place_queries import PlaceQueryCache, canonical_district
from backend.app.models.pet import Place, RestaurantDetails
from backend.app.services.pet_service import select_places
from test_pet_data import service


def restaurant(i, **extra):
    return Place(id=f'restaurant:{i}', category='restaurants', name=f'Restaurant {i}',
                 source_url='https://example.org/restaurants', source_name='Saved source',
                 district='九龍城', cuisines=['日式', '咖啡／輕食'],
                 cuisine_source='https://example.org/cuisines',
                 latitude=22.3 + i * .00001, longitude=114.17,
                 restaurant_details=RestaurantDetails(google_place_id=f'google{i}',
                     rating=4.1 + i * .001, rating_count=i + 1,
                     price_range={'endPrice': {'units': str(100 + i)}}), **extra)


async def close(svc, cache, client):
    await svc.place_query_cache.aclose()
    await cache.aclose()
    await client.aclose()


def test_queries_across_users_and_aliases_share_results_without_leaking_mutations(tmp_path):
    async def run():
        svc, cache, client = service(tmp_path)
        svc.snapshot.places = [restaurant(i) for i in range(160)]
        try:
            with patch('backend.app.services.pet_service.select_places', wraps=select_places) as select:
                first = await PetDataAccess(svc).search_places(mode='restaurant', cuisine='Japanese',
                    district='Kowloon City District', sort_by='rating', min_rating=4, limit=2)
                assert first['total'] == 160
                assert first['items'][0]['id'] == 'restaurant:159'
                first['items'][0]['name'] = 'Changed by one caller'
                first['items'][0]['restaurant_details']['rating'] = 0
                another_user = PetDataAccess(svc)
                again = await another_user.search_places(mode='restaurants', cuisine='日式',
                    district='九龍城區', sort_by='rating', min_rating=4.0, limit=2)
                assert select.call_count == 1
                assert again['items'][0]['name'] == 'Restaurant 159'
                assert again['items'][0]['restaurant_details']['rating'] > 4
                assert again['sources'] and another_user.lookup_sources
                assert 'restaurant:159' in another_user.seen_places
                assert 'restaurant:159' in {p['id'] for p in another_user.mentioned_places('Restaurant 159')}
        finally:
            await close(svc, cache, client)
    asyncio.run(run())


def test_facilities_and_unrated_places_are_retained_and_index_is_not_serialized_again(tmp_path):
    async def run():
        svc, cache, client = service(tmp_path)
        svc.snapshot.places = [restaurant(0), Place(id='mall:1', category='malls', name='Shopping Mall',
            district='九龍城', source_url='https://example.org/mall', source_name='Third-party directory',
            latitude=22.301, longitude=114.17, notes=['Confirm tenant restrictions'], pet_policy='conditional',
            mall_policy={'tier':'carrier_only','verification':'third_party',
                         'listing_url':'https://example.org/mall','listing_updated_at':'2026-10-30'})]
        try:
            await PetDataAccess(svc).search_places(cuisine='日式')
            # A different query must reuse the all-venue index, not just the first result.
            with patch.object(Place, 'model_dump', side_effect=AssertionError('Rebuilt published index')):
                result = await PetDataAccess(svc).search_places(mode='facilities', category='malls', district='Kowloon')
                assert result['total'] == 1 and result['items'][0]['id'] == 'mall:1'
                assert not result['items'][0].get('restaurant_details')
                assert result['items'][0]['notes'] == ['Confirm tenant restrictions']
                assert result['items'][0]['pet_policy'] == 'conditional'
                assert result['items'][0]['mall_policy']['tier'] == 'carrier_only'
                assert result['items'][0]['mall_policy']['verification'] == 'third_party'
        finally:
            await close(svc, cache, client)
    asyncio.run(run())


def test_actual_coordinates_radius_sort_limit_and_review_policy_do_not_collide(tmp_path):
    async def run():
        svc, cache, client = service(tmp_path)
        svc.snapshot.places = [restaurant(0), restaurant(10)]
        svc.snapshot.places[1].restaurant_details.match_status = 'needs_review'
        try:
            async def search(origin, **kwargs):
                return await PetDataAccess(svc, origin=origin).search_places(mode='restaurants', **kwargs)
            a = await search((22.3, 114.17), sort_by='distance', radius_m=3, limit=1)
            b = await search((22.3001, 114.17), sort_by='distance', radius_m=3, limit=1)
            assert a['items'][0]['id'] == 'restaurant:0'
            assert b['items'][0]['id'] == 'restaurant:10'
            assert a['origin'] != b['origin']
            assert (await search((22.3, 114.17), sort_by='distance', radius_m=20, limit=2))['total'] == 2
            rating = await search((22.3, 114.17), sort_by='rating', limit=1)
            assert rating['items'][0]['id'] == 'restaurant:10'
            matched = await search((22.3, 114.17), sort_by='rating', limit=1, exclude_review_candidates=True)
            assert matched['items'][0]['id'] == 'restaurant:0'
            assert len((await search((22.3, 114.17), limit=2))['items']) == 2
            assert (await search((22.3, 114.17), max_price=105))['total'] == 1
        finally:
            await close(svc, cache, client)
    asyncio.run(run())


def test_published_revision_and_data_status_invalidate_cached_results(tmp_path, monkeypatch):
    async def run():
        svc, cache, client = service(tmp_path)
        svc.snapshot.places = [restaurant(0)]
        try:
            first = await PetDataAccess(svc).search_places(sort_by='rating')
            svc.snapshot = svc.snapshot.model_copy(update={'places': [restaurant(1)]}, deep=True)
            second = await PetDataAccess(svc).search_places(sort_by='rating')
            assert first['items'][0]['id'] != second['items'][0]['id']
            monkeypatch.setattr(svc, '_status', lambda: 'stale')
            third = await PetDataAccess(svc).search_places(sort_by='rating')
            assert third['status'] == 'stale' and third['items'] == second['items']
        finally:
            await close(svc, cache, client)
    asyncio.run(run())


def test_result_is_shared_with_another_service_and_expiry_is_bounded(tmp_path):
    async def run():
        svc, cache, client = service(tmp_path)
        other, other_cache, other_client = service(tmp_path)
        svc.snapshot.places = [restaurant(0)]
        other.snapshot = svc.snapshot.model_copy(deep=True)
        # Both workers use the same namespaced shared store, not the same L1.
        await other.place_query_cache.aclose()
        other.place_query_cache = PlaceQueryCache(cache)
        try:
            first = await PetDataAccess(svc).search_places(cuisine='Japanese')
            with patch('backend.app.services.pet_service.select_places', side_effect=AssertionError('Shared hit recomputed')):
                second = await PetDataAccess(other).search_places(cuisine='日式')
            assert first == second
            assert len(other.place_query_cache.local._data) == 1
            entries = list(cache.fallback._data.items())
            assert len(entries) == 1 and entries[0][1][0] is not None
        finally:
            await close(other, other_cache, other_client)
            await close(svc, cache, client)
    asyncio.run(run())


def test_random_draws_bypass_result_cache_and_fast_answers_use_shared_filter_cache(tmp_path, monkeypatch):
    async def run():
        svc, cache, client = service(tmp_path)
        svc.snapshot.places = [restaurant(0), restaurant(1)]
        draws = []
        def sample(self, population, count):
            draws.append(len(population))
            return population[:count]
        monkeypatch.setattr('agent.data.place_search.random.SystemRandom.sample', sample)
        try:
            for _ in range(2):
                await PetDataAccess(svc).search_places(sort_by='random', limit=1)
            assert draws == [2, 2] and not cache.fallback._data
            with patch('backend.app.services.pet_service.select_places', wraps=select_places) as select:
                a = await fast_answer('Find dog-friendly cafés in Kowloon City, with source links.', [], PetDataAccess(svc), 'en')
                b = await fast_answer('我想帶狗去九龍城飲咖啡，幫我搵有資料來源嘅餐廳。', [], PetDataAccess(svc), 'zh-Hant')
                assert a['places'] and b['places'] and select.call_count == 1
        finally:
            await close(svc, cache, client)
    asyncio.run(run())


def test_stalled_optional_cache_cannot_block_an_answer():
    class Stalled:
        async def get_json(self, key):
            await asyncio.Event().wait()
        async def set_json(self, *args):
            await asyncio.Event().wait()
    async def run():
        cache = PlaceQueryCache(Stalled())
        try:
            result = await asyncio.wait_for(cache.get_or_create('revision', {}, lambda: {'items': [{'id':'a'}]}), 1)
            assert result['items'][0]['id'] == 'a'
            # A second request is an L1 hit even while Redis is still stalled.
            assert await cache.get_or_create('revision', {}, lambda: pytest.fail('L1 miss')) == result
        finally:
            await cache.aclose()
    asyncio.run(run())


def test_overlapping_users_share_a_fill_and_one_cancelled_waiter_does_not_cancel_the_others():
    class Delayed:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
        async def get_json(self, key):
            self.entered.set()
            await self.release.wait()
        async def set_json(self, *args):pass
    async def run():
        shared = Delayed()
        cache = PlaceQueryCache(shared)
        fills = []
        def fill():
            fills.append(True)
            return {'items': [{'id':'a'}]}
        try:
            a = asyncio.create_task(cache.get_or_create('v', {}, fill))
            await shared.entered.wait()
            b = asyncio.create_task(cache.get_or_create('v', {}, fill))
            await asyncio.sleep(0)
            a.cancel()
            with pytest.raises(asyncio.CancelledError):await a
            shared.release.set()
            result = await b
            result['items'].clear()
            assert (await cache.get_or_create('v', {}, fill))['items'] == [{'id':'a'}]
            assert len(fills) == 1
        finally:
            await cache.aclose()
    asyncio.run(run())


def test_local_capacity_evicts_old_entries_and_alias_keys_are_canonical():
    async def run():
        from backend.app.cache.redis_cache import RedisCache
        shared = RedisCache(None, 'bounded-query-test')
        cache = PlaceQueryCache(shared)
        cache.local.max_entries = 2
        try:
            for i in range(3):
                await cache.get_or_create('v', {'query':str(i)}, lambda: {'items':[]})
            assert len(cache.local._data) == 2 and cache.local._bytes <= cache.local.max_bytes
            keys = list(shared.fallback._data)
            assert all(re.fullmatch(r'bounded-query-test:place-query:v1:[0-9a-f]{64}', key) for key in keys)
            assert len(keys) == 3
            assert canonical_district('Kowloon City District') == canonical_district('九龍城區')
            assert canonical_district('Hong Kong Island') == canonical_district('港島')
            assert canonical_district('區') != canonical_district('')
        finally:
            await cache.aclose()
            await shared.aclose()
    asyncio.run(run())


def test_snapshot_replacement_during_cache_read_keeps_version_and_payload_consistent(tmp_path):
    async def run():
        svc, shared, client = service(tmp_path)
        svc.snapshot.places = [restaurant(0)]
        entered = asyncio.Event()
        release = asyncio.Event()
        async def delayed_read(key):
            entered.set()
            await release.wait()
            return None
        try:
            with patch.object(shared, 'get_json', delayed_read):
                old_read = asyncio.create_task(PetDataAccess(svc).search_places(sort_by='rating'))
                await entered.wait()
                svc.snapshot = svc.snapshot.model_copy(update={'places': [restaurant(1)]}, deep=True)
                release.set()
                assert (await old_read)['items'][0]['id'] == 'restaurant:0'
            assert (await PetDataAccess(svc).search_places(sort_by='rating'))['items'][0]['id'] == 'restaurant:1'
        finally:
            await close(svc, shared, client)
    asyncio.run(run())


def test_separate_redis_clients_share_query_results_with_expiry():
    import fakeredis.aioredis
    from backend.app.cache.redis_cache import RedisCache
    async def run():
        server = fakeredis.FakeServer()
        one = RedisCache(fakeredis.aioredis.FakeRedis(server=server), 'place-cache-test')
        two = RedisCache(fakeredis.aioredis.FakeRedis(server=server), 'place-cache-test')
        first, second = PlaceQueryCache(one), PlaceQueryCache(two)
        try:
            result = await first.get_or_create('snapshot', {'cuisine':'日式'}, lambda: {'items':[{'id':'r1'}]})
            assert await second.get_or_create('snapshot', {'cuisine':'日式'}, lambda: pytest.fail('Redis hit recomputed')) == result
            key = one._key(first.key('snapshot', {'cuisine':'日式'}))
            assert 0 < await one.client.ttl(key) <= 600
            assert not one.fallback._data and not two.fallback._data
        finally:
            await first.aclose()
            await second.aclose()
            await one.aclose()
            await two.aclose()
    asyncio.run(run())


def test_capabilities_identify_the_deployed_saved_query_cache(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.config.settings import Settings
    from backend.app.config.container import Container
    from main import app
    svc, cache, client = service(tmp_path)
    app.state.container = Container(Settings(api_key='', model='test', base_url='https://example.invalid',
                                             cors_origins=[]), cache, client, svc)
    async def ensure():pass
    monkeypatch.setattr(svc, 'ensure', ensure)
    try:
        with TestClient(app) as api:
            response = api.get('/api/v1/assistant/capabilities')
            assert response.status_code == 200
            assert response.json()['saved_place_queries'] == {
                'coverage':['restaurants','facilities'],'cache_version':'place-query:v1',
                'result_ttl_seconds':600,'random_results_cached':False}
    finally:
        del app.state.container
