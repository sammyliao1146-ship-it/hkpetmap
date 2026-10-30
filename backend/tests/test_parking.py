import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from backend.app.cache.redis_cache import RedisCache
from backend.app.config.factory import create_app
from backend.app.config.middleware import register_middleware
from backend.app.config.settings import Settings
from backend.app.services.parking_service import ParkingService


def test_bilingual_parking_cache_radius_and_stale_vacancy(tmp_path):
    calls = []
    def upstream(request):
        calls.append(dict(request.url.params))
        if request.url.params['data']=='vacancy':
            return httpx.Response(200,json={'results':[{'park_Id':'12','privateCar':[{'vacancy':14,'vacancy_type':'A','lastupdate':'2020-01-01 12:00:00'}]}]})
        name = 'Amoy Plaza' if request.url.params['lang']=='en_US' else '淘大商場'
        return httpx.Response(200,json={'results':[{
            'park_Id':'12','name':name,'displayAddress':'77 Ngau Tau Kok Road',
            'latitude':22.3247,'longitude':114.21675,
            'privateCar':{'hourlyCharges':[{'price':25}]},'heightLimits':[{'height':1.9}],
        }]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            service=ParkingService(RedisCache(None,'parking-test'),client,tmp_path/'parking.json')
            en=await service.list();zh=await service.list('zh-Hant')
            assert len(calls)==3
            p=en['items'][0]
            assert p['id']=='parking:12' and p['name']=='Amoy Plaza'
            assert p['name_zh']=='淘大商場' and zh['items'][0]['name']=='淘大商場'
            assert p['vacancy']==14 and p['vacancy_status']=='stale'
            assert p['height_limits']==[{'height':1.9}] and p['fee_summary']=='HK$25/hour'
            assert (await service.nearby(22.3247,114.21675))['items'][0]['distance_m']==0
            assert not (await service.nearby(22.4,114.2,radius_m=1000))['items']
    asyncio.run(run())


def test_vacancy_freshness_does_not_treat_unknown_as_full():
    now=datetime.now(ZoneInfo('Asia/Hong_Kong'))
    fresh=(now-timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S')
    assert ParkingService._vacancy({'privateCar':[{'vacancy':0,'lastupdate':fresh}]},now)[2]=='full'
    assert ParkingService._vacancy({'privateCar':[{'vacancy':5,'lastupdate':fresh}]},now)[2]=='available'
    assert ParkingService._vacancy({'privateCar':[{'vacancy':-1,'lastupdate':fresh}]},now)==(None,fresh,'unknown')
    assert ParkingService._vacancy({},now)==(None,None,'unknown')


def test_cold_planning_uses_bundled_government_locations_without_live_vacancy_or_fetch(tmp_path):
    async def run():
        async def forbidden(request):raise AssertionError('Planning contacted the parking upstream')
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
            service=ParkingService(RedisCache(None,'parking-cold-test'),client,tmp_path/'absent.json')
            result=await service.list(refresh=False)
            assert result['status']=='cached' and result['items']
            assert all(p['vacancy'] is None and p['vacancy_status']=='unknown' for p in result['items'])
            assert all(p['source_url'].startswith('https://data.gov.hk/') for p in result['items'])
    asyncio.run(run())


def test_upstream_failure_uses_snapshot_and_backs_off(tmp_path):
    calls=[]
    def unavailable(request):
        calls.append(request)
        return httpx.Response(503)
    async def run():
        cache=RedisCache(None,'parking-test')
        await cache.set_json('parking:v1',{'info_en':[{'park_Id':'1','name':'Last known park','latitude':22.3,'longitude':114.1}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
            service=ParkingService(cache,client,tmp_path/'parking.json')
            one=await service.list();two=await service.list()
            assert one['status']==two['status']=='partial'
            assert one['items'][0]['name']=='Last known park'
            assert len(calls)==3
    asyncio.run(run())


def test_middleware_allows_production_domain_even_with_local_env():
    from fastapi import FastAPI
    app=FastAPI()
    register_middleware(app,Settings(api_key='',model='test',base_url='https://example.invalid',cors_origins=['http://localhost:5174']),'/api/v1')
    with TestClient(app) as client:
        for origin in ['https://hkpetmap.com','https://www.hkpetmap.com']:
            r=client.options('/api/v1/parking',headers={'Origin':origin,'Access-Control-Request-Method':'GET'})
            assert r.status_code==200 and r.headers['access-control-allow-origin']==origin
        assert client.options('/api/v1/parking',headers={'Origin':'https://evil.invalid','Access-Control-Request-Method':'GET'}).status_code==400
