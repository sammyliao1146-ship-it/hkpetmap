import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import ValidationError

from agent.data_access import PetDataAccess
from backend.app.cache.redis_cache import RedisCache
from backend.app.data.malls import load_malls, merge_malls
from backend.app.models.pet import MallPolicy, Place, Snapshot
from backend.app.services.pet_service import PetService


def test_manifest_has_57_unique_bilingual_mapped_places_with_provenance():
    malls=load_malls()
    assert len(malls)==len({p.id for p in malls})==57
    assert all(p.name_en and p.address and p.address_en and p.latitude and p.longitude for p in malls)
    assert all(p.mall_policy.listing_updated_at=='2026-09-17' for p in malls)
    assert sum(p.mall_policy.verification=='official_checked' for p in malls)==2
    assert all(p.pet_policy=='conditional' for p in malls if p.mall_policy.verification=='third_party')
    airside=[p for p in malls if p.name_en=='AIRSIDE']
    assert len(airside)==1 and airside[0].id=='curated:airside'


def test_source_location_and_name_errors_are_corrected():
    by_name={p.name_en:p for p in load_malls()}
    assert 22.33 < by_name['SOGO Kai Tak'].latitude < 22.34
    assert 22.30 < by_name['MONTEREY Place'].latitude < 22.31
    assert by_name['Tsuen Wan Plaza'].website.host=='www.tsuenwanplaza.com.hk'
    assert by_name['Citywalk'].name=='荃新天地'
    assert by_name['GO PARK Sai Sha'].district=='大埔區'
    assert by_name['Ma Wan 1868'].district=='荃灣區'
    assert '2至4樓' in ' '.join(by_name['IFC Mall'].notes)


def test_official_claim_requires_evidence():
    with pytest.raises(ValidationError):
        MallPolicy(tier='designated_zone',verification='official_checked',listing_url='https://example.com/',listing_updated_at='2026-09-17')


def test_cached_load_and_agent_details_include_malls_without_duplicates(tmp_path):
    async def run():
        cache=RedisCache(None,'mall-test')
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(503)))
        svc=PetService(cache,client,tmp_path/'snapshot.json')
        old=Place(id='curated:airside',category='malls',name='old',source_name='test',source_url='https://example.com/')
        snapshot=Snapshot(fetched_at=datetime.now(ZoneInfo('Asia/Hong_Kong')),places=[old],activities=[],sources=[])
        await cache.set_json('snapshot:v1',snapshot.model_dump(mode='json'),ttl=60)
        try:
            await svc.load()
            assert svc.places(categories=['malls'])['total']==57
            svc.snapshot.places=merge_malls(svc.snapshot.places)
            assert len(svc.snapshot.places)==57
            agent=PetDataAccess(svc)
            results=await agent.search_places(category='malls',query='IFC')
            assert results['total']==1
            details=await agent.place_details(results['items'][0]['id'])
            assert details['place']['mall_policy']['verification']=='official_checked'
            assert details['remaining'] is None
            curated,_=await svc._curated()
            assert all(p.category!='malls' for p in curated)
        finally:
            await client.aclose();await cache.aclose()
    asyncio.run(run())
