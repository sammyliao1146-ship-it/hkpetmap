import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.data_access import PetDataAccess
from agent.prompts import instructions_for_language
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from backend.app.data.adapters import normalize_layer
from backend.app.data.localization import enrich_english
from backend.app.data.sources import LAYERS
from backend.app.models.assistant import ChatRequest
from backend.app.models.pet import Activity, Place
from backend.tests.test_pet_data import service
from main import app


def test_language_is_validated_and_defaults_to_cantonese():
    assert ChatRequest(message='hello').language=='zh-Hant'
    assert ChatRequest(message='hello',language='en').language=='en'
    with pytest.raises(ValidationError):ChatRequest(message='hello',language='fr')
    assert 'Respond in clear English for this request' in instructions_for_language('en')
    assert instructions_for_language('zh-Hant').endswith('即使之前對話使用英文。')
    with pytest.raises(ValueError):instructions_for_language('fr')


def test_english_guidance_keeps_original_data_and_unknowns():
    p=Place(id='v:1',category='vets',name='原名',source_name='漁護署獸醫診所名單',source_url='https://www.pets.gov.hk/',notes=['自願列入嘅診所名錄，唔係醫院牌照認證。','未翻譯嘅原始備註'])
    a=Activity(id='a:1',name='課程',name_en='Puppy Socialization Course',dates_text='Nov 10',description='原始中文介紹',fee_text='會員：$2,200 非會員：$2,600',source_name='香港愛護動物協會 SPCA',source_url='https://www.spca.org.hk/')
    enrich_english([p],[a])
    assert p.name_en is None and p.notes[-1]=='未翻譯嘅原始備註'
    assert p.notes_en==['This is a voluntary clinic directory, not a hospital licensing certification.']
    assert a.description_en is None and a.remaining is None
    assert a.fee_text_en=='Member: $2,200 Non-member: $2,600'
    enrich_english([p],[a])
    assert len(p.notes_en)==1  # Loading twice must not duplicate translated guidance.


def test_official_english_fields_are_preserved():
    layer=next(l for l in LAYERS if l.category=='pet_parks')
    p=normalize_layer(layer,{'properties':{'OBJECTID':9,'NameTC':'公園','NameEN':'Example Park','OpeningHoursTC':'每日開放','OpeningHoursEN':'Open daily','WebsiteEN':'https://www.lcsd.gov.hk/en/park','FacilityDetailsEN':'Dog waste bins'},'geometry':{'type':'Point','coordinates':[114.1,22.3]}})
    assert p.name_en=='Example Park' and p.opening_hours_en=='Open daily'
    assert p.notes_en==['Dog waste bins']
    assert str(p.website_en)=='https://www.lcsd.gov.hk/en/park'


def test_chat_forwards_language_and_preserves_history(tmp_path,monkeypatch):
    svc,cache,client=service(tmp_path)
    settings=Settings(api_key='unit-test-no-network',model='test',base_url='https://example.invalid/v1',cors_origins=[],cache_prefix='pet-test')
    app.state.container=Container(settings,cache,client,svc)
    captured=[]
    async def no_refresh():pass
    async def answer(message,**kwargs):
        captured.append((message,kwargs))
        return 'English reply' if kwargs['language']=='en' else '粵語回覆'
    monkeypatch.setattr(svc,'ensure',no_refresh)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant',answer)
    from agent.intent_router import IntentDecision
    async def classify(*args,**kwargs):
        return IntentDecision(intent='map_query',map_mode='general',confidence=.95)
    async def approve(**kwargs):return True
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent',classify)
    monkeypatch.setattr('backend.app.routers.assistant.review_answer',approve)
    try:
        with TestClient(app) as api:
            history=[{'role':'user','content':'原有條件'}]
            r=api.post('/api/v1/assistant/chat',json={'message':'Find a park','language':'en','history':history})
            assert r.status_code==200 and r.json()['answer']=='English reply'
            assert captured[0][1]['language']=='en' and captured[0][1]['history']==history
            assert api.post('/api/v1/assistant/chat',json={'message':'搵公園'}).json()['answer']=='粵語回覆'
            assert api.post('/api/v1/assistant/chat',json={'message':'hi','language':'fr'}).status_code==422
    finally:
        del app.state.container


def test_sdk_agent_receives_english_directive_without_network(tmp_path,monkeypatch):
    from agent import service as sdk
    svc,cache,client=service(tmp_path)
    captured=[]
    async def fake_run(agent,messages,**kwargs):
        captured.append((agent,messages))
        return SimpleNamespace(final_output='English reply')
    monkeypatch.setattr(sdk.Runner,'run',fake_run)
    async def run():
        try:
            result=await sdk.run_pet_assistant('Find a park',api_key='unit-test-no-network',base_url='https://example.invalid/v1',model='test',access=PetDataAccess(svc),language='en',history=[{'role':'user','content':'原有條件'}])
            assert result=='English reply'
            assert 'Respond in clear English for this request' in captured[0][0].instructions
            assert captured[0][1][0]['content']=='原有條件'
        finally:
            await client.aclose();await cache.aclose()
    asyncio.run(run())
