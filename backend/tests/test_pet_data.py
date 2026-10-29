import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from agents import function_tool
from fastapi.testclient import TestClient

from agent.data.data_access import PetDataAccess
from agent.data.tools.pet_data import make_pet_queries
from backend.app.cache.redis_cache import RedisCache
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from backend.app.data.adapters import normalize_hotels, normalize_layer, normalize_restaurants, parse_courses, parse_vets, safe_url
from backend.app.data.sources import LAYERS
from backend.app.models.pet import Activity, Place, Snapshot
from backend.app.services.pet_service import PetService
from main import app

HK=ZoneInfo('Asia/Hong_Kong')
URL='https://www.pets.gov.hk/'


def place(id='park:1', **kwargs):
    return Place(id=id, category='pet_parks', name='寵物公園', source_url=URL, source_name='測試來源', **kwargs)


def service(tmp_path):
    cache=RedisCache(None,'pet-test')
    client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(503)))
    svc=PetService(cache,client,tmp_path/'snapshot.json')
    svc.snapshot=Snapshot(fetched_at=datetime.now(HK),places=[place(),Place(id='restaurant:1',category='restaurants',name='餐廳',source_url=URL,source_name='食環署')],
        activities=[Activity(id='course:1',name='幼犬社交班',dates_text='Nov 10',description='公開課程',source_url=URL,source_name='SPCA')],sources=[])
    return svc,cache,client


def test_missing_cuisine_and_coordinates_are_unknown():
    items=normalize_restaurants([{'licence':'3152804436','shop_sign_tc':'餐廳','address_tc':'香港地址'}],[])
    assert items[0].cuisines==[]
    assert items[0].latitude is None
    assert items[0].pet_policy=='dogs_permitted'
    with pytest.raises(ValueError):
        place(latitude=22.3)
    with pytest.raises(ValueError):
        place(cuisines=['日式'])


def test_restaurant_coordinates_join_by_licence_not_name():
    points=[{'properties':{'SEARCH02_TC':'3152804436'},'geometry':{'type':'Point','coordinates':[114.1,22.3]}}]
    rows=[{'licence':'3152804436','shop_sign_tc':'新店名'},{'licence':'3152804437','shop_sign_tc':'新店名'}]
    result=normalize_restaurants(rows,points)
    assert result[0].latitude==22.3
    assert result[1].latitude is None


def test_general_park_is_not_dog_friendly():
    layer=next(l for l in LAYERS if l.category=='parks')
    p=normalize_layer(layer,{'properties':{'OBJECTID':1,'NameTC':'公園'},'geometry':{'type':'Point','coordinates':[114.1,22.3]}})
    assert p.pet_policy=='unknown'
    assert any('唔代表' in n for n in p.notes)


def test_hotels_script_is_parsed_as_json_never_executed():
    with pytest.raises(ValueError):normalize_hotels('alert(1)')
    with pytest.raises(ValueError):normalize_hotels('var pet_hotel_data={}; fetch("https://evil.invalid")')


def test_course_dates_require_a_source_year_and_remaining_is_unknown():
    row='<table><tr><th>Course Code</th><th>Enrol</th></tr><tr><td>A2479</td><td>Puppy Socialization Course</td><td>Class 1: Nov 10 (Tue) Class 2 – 5: Nov 14 – Dec 5 (Every Sat)</td><td>English</td><td>Member: $2,200</td><td>Hong Kong Centre</td><td><a href="https://dogtrainbook.spca.org.hk/enrol/200">ENROLL</a></td></tr></table>'
    course=parse_courses('<a href="schedule.pdf">Nov – Dec 2026</a>'+row)[0]
    assert course.start_date=='2026-11-10' and course.end_date=='2026-12-05'
    assert course.remaining is None and course.place_id=='curated:spca-wan-chai'
    assert parse_courses(row)[0].start_date is None
    assert safe_url('javascript:alert(1)') is None
    assert safe_url('https://user:password@example.com') is None


def test_vet_pdf_columns_match_real_official_sample():
    result=parse_vets((Path(__file__).parent/'fixtures/vets_first_page.pdf').read_bytes(),URL)
    assert len(result)==11
    assert result[0].name=='動物醫療學會醫院'
    assert result[0].telephone=='3899 8999'
    assert '加連威老道100號' in result[0].address
    assert result[0].district=='油尖旺區'


def test_filters_and_agent_tools_share_same_snapshot(tmp_path):
    async def run():
        svc,cache,client=service(tmp_path)
        try:
            access=PetDataAccess(svc)
            result=await access.search_places(mode='restaurants',cuisine='未分類')
            assert result['total']==1 and result['items'][0]['name']=='餐廳'
            assert svc.places(categories=['vets'])['total']==0
            course=(await access.activity_details('course:1'))['activity']
            assert course['remaining'] is None
            assert (await access.place_details('missing'))['found'] is False
            tools=[function_tool(q) for q in make_pet_queries(access)]
            assert {t.name for t in tools}=={'get_pet_catalog','search_pet_places','get_pet_place_details','search_pet_activities','get_pet_activity_details','get_pet_transport','get_pet_directions','get_pet_parking'}
            assert all('sports' not in t.name for t in tools)
            with pytest.raises(ValueError):await access.search_places(limit=1000)
        finally:
            await client.aclose();await cache.aclose()
    asyncio.run(run())


def test_failed_refresh_preserves_records_and_source_timestamp(tmp_path):
    async def run():
        svc,cache,client=service(tmp_path)
        old_time=(datetime.now(HK)-timedelta(days=2)).isoformat()
        svc.snapshot.sources=[{'key':'restaurants','fetched_at':old_time}]
        try:
            await svc.refresh(force=True)
            restaurant=next(s for s in svc.snapshot.sources if s['key']=='restaurants')
            assert restaurant['status']=='stale' and restaurant['fetched_at']==old_time
            assert any(p.id=='restaurant:1' for p in svc.snapshot.places)
            assert (await PetDataAccess(svc).place_details('restaurant:1'))['remaining'] is None
            assert svc.catalogue()['status']=='partial'
        finally:
            await client.aclose();await cache.aclose()
    asyncio.run(run())


def test_http_contract_validation_and_missing_model_key(tmp_path,monkeypatch):
    svc,cache,client=service(tmp_path)
    settings=Settings(api_key='',model='test',base_url='https://example.com/v1',cors_origins=[],cache_prefix='pet-test')
    app.state.container=Container(settings,cache,client,svc)
    async def no_refresh():pass
    monkeypatch.setattr(svc,'ensure',no_refresh)
    try:
        with TestClient(app) as api:
            assert api.get('/api/v1/health').json()['application']=='hk-petfinder'
            assert api.get('/api/v1/places?mode=restaurants&cuisine=未分類').json()['total']==1
            assert api.get('/api/v1/places?mode=sports').status_code==422
            assert api.get('/api/v1/places?category=badminton').status_code==422
            assert api.get('/api/v1/places/missing').status_code==404
            assert api.get('/api/v1/activities').json()['items'][0]['remaining'] is None
            capabilities=api.get('/api/v1/assistant/capabilities').json()
            assert len(capabilities['tools'])==9
            assert capabilities['answer_guard']['fail_closed'] is True
            assert api.post('/api/v1/assistant/chat',json={'message':'搵餐廳'}).status_code==503
            assert api.post('/api/v1/assistant/chat',json={'message':'   '}).status_code==422
    finally:
        del app.state.container
