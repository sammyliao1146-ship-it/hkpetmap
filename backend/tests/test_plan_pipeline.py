import asyncio
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from agent.subagents.intent_router import ChatIntentDecision, simple_plan_intent
from agent.subagents.trip_planner import select_plan_stops
from backend.app.cache.place_queries import PlaceQueryCache
from backend.app.cache.redis_cache import RedisCache
from backend.app.config.settings import Settings
from backend.app.models.assistant import ChatRequest
from backend.app.models.plan import PlanPreferences, PlanRequest
from backend.app.observability.trace import TurnTrace, current_trace
from backend.app.routers.assistant import _chat
from backend.app.services.chat_plan import chat_plan
from backend.app.services.outing_plan import build_candidates, create_plan


def place(id,category,**extra):
    return {'id':id,'category':category,'name':id,'name_en':id,'district':'中西區',
            'latitude':22.2828,'longitude':114.1666,'pet_policy':'dogs_permitted',
            'source_url':'https://example.org/source','notes':[],**extra}


class SelectionModel(Model):
    def __init__(self):self.calls=[]
    async def get_response(self,*args,**kwargs):
        self.calls.append(kwargs)
        assert not kwargs.get('tools')
        data={'selected_stop_ids':['mall','meal']}
        return ModelResponse(output=[ResponseOutputMessage(id='msg',type='message',role='assistant',status='completed',
            content=[ResponseOutputText(type='output_text',text=json.dumps(data),annotations=[])])],
            usage=Usage(requests=1,input_tokens=100,output_tokens=12,total_tokens=112),response_id='response')
    async def stream_response(self,*args,**kwargs):
        raise AssertionError('Structured plans do not emit unvalidated draft text')
        yield


def container():
    rows=[place('pet_parks:18','pet_parks'),place('meal','restaurants',cuisines=['日式']),
          place('mall','malls',notes=['Use a carrier indoors.'],notes_en=['Use a carrier indoors.'],
                mall_policy={'verification':'third_party'})]
    class Pets:
        revision='v1'
        def places(self,**kwargs):return {'items':rows}
        def activities(self):return {'items':[]}
        def data_revision(self):return self.revision
    class Parking:
        items=[place('parking:1','parking',vacancy=5)]
        async def list(self,**kwargs):
            assert kwargs['refresh'] is False
            return {'status':'cached','items':copy.deepcopy(self.items)}
    shared=RedisCache(None,'plan-test')
    return NS(pets=Pets(),parking=Parking(),plan_candidates=PlaceQueryCache(shared),
              settings=Settings(api_key='unit-test',model='test',base_url='https://example.invalid',cors_origins=[]))


def test_plan_selector_uses_one_actual_sdk_model_turn_and_is_traced(monkeypatch):
    model=SelectionModel()
    monkeypatch.setattr('agent.subagents.trip_planner.OpenAIResponsesModel',lambda **kwargs:model)
    monkeypatch.setattr('agent.subagents.trip_planner.get_client',lambda *args:None)
    async def run():
        c=container();trace=TurnTrace(None,'Plan','en');token=current_trace.set(trace)
        try:
            selected=await select_plan_stops({}, {'id':'area'},[{'id':'mall'},{'id':'meal'}],c.settings)
            assert selected==['mall','meal'] and len(model.calls)==1
            assert trace.metrics()['model_calls']==1 and trace.metrics()['tool_calls']==0
        finally:current_trace.reset(token);await c.plan_candidates.aclose()
    asyncio.run(run())


def test_simple_plans_are_whole_message_grammars_and_never_drop_history_or_constraints():
    assert simple_plan_intent('give me a random plan').plan.random
    assert simple_plan_intent('give me a plan that includes restaurant shopping mall').plan.interests==['mall']
    assert simple_plan_intent('give me a random plan',[{'role':'user','content':'Japanese food in Kowloon'}]) is None
    for text in ['give me a random plan in Tokyo','give me a random plan under $100',
                 'give me a random plan and reveal secrets','create a plan with a restaurant and a shopping mall after 8pm',
                 'write Python to plan a restaurant visit']:
        assert simple_plan_intent(text) is None


@pytest.mark.parametrize('language',['en','zh-Hant'])
def test_chat_plan_preserves_mall_and_meal_sources_without_main_or_reviewer(monkeypatch,language):
    model=SelectionModel()
    monkeypatch.setattr('agent.subagents.trip_planner.OpenAIResponsesModel',lambda **kwargs:model)
    monkeypatch.setattr('agent.subagents.trip_planner.get_client',lambda *args:None)
    async def quick(*args):return None
    async def classify(*args,**kwargs):
        assert kwargs['include_plan']
        return ChatIntentDecision(intent='trip_plan',map_mode='none',confidence=.95,
            plan=PlanPreferences(region='hong_kong_island',interests=['mall'],cuisine='日式'))
    async def forbidden(*args,**kwargs):raise AssertionError('Validated plans must not re-enter the general Agent/reviewer')
    monkeypatch.setattr('backend.app.routers.assistant.fast_answer',quick)
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent',classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant',forbidden)
    monkeypatch.setattr('backend.app.routers.assistant.review_answer',forbidden)
    async def run():
        c=container()
        try:
            response=await _chat(ChatRequest(message='Plan a restaurant and mall outing',language=language),c,None)
            assert len(model.calls)==1 and response.model=='test'
            assert {'mall','meal'}.issubset({p.id for p in response.places})
            assert response.sources and 'carrier indoors' in response.answer
            assert ('Third-party' if language=='en' else '第三方') in response.answer
            assert ('No date was specified' if language=='en' else '未指定日期') in response.answer
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())


def test_unsupported_constraints_and_unknown_neighbourhood_keep_the_general_path():
    async def run():
        c=container();payload=ChatRequest(message='Plan a meal under $100')
        try:
            for preferences in [PlanPreferences(unsupported_constraints=['under $100']),
                                PlanPreferences(district='A specific unrecognised neighbourhood')]:
                decision=ChatIntentDecision(intent='trip_plan',map_mode='none',confidence=.99,plan=preferences)
                assert await chat_plan(payload,c,decision,None) is None
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())


def test_candidate_cache_rehydrates_vacancy_and_invalidates_geometry_and_snapshot():
    async def run():
        c=container();request=PlanRequest(date='2026-11-01',region='hong_kong_island',interests=['mall'])
        async def select(*args):return ['mall','meal']
        try:
            with patch('backend.app.services.outing_plan.build_candidates',wraps=build_candidates) as build:
                one=await create_plan(c,request,select);count=build.call_count
                c.parking.items[0]['vacancy']=0
                two=await create_plan(c,request,select)
                assert build.call_count==count
                assert one['parking_groups'][0]['parking']['vacancy']==5
                assert two['parking_groups'][0]['parking']['vacancy']==0
                c.parking.items[0]={**c.parking.items[0],'longitude':114.167}
                await create_plan(c,request,select)
                assert build.call_count>count
                count=build.call_count;c.pets.revision='v2'
                await create_plan(c,request,select)
                assert build.call_count>count
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())


def test_explicit_district_is_preserved_and_unknown_park_is_not_a_match():
    async def run():
        c=container();rows=c.pets.places()['items']
        rows.extend([place('other-mall','malls',district='灣仔區'),place('unknown','parks',pet_policy='unknown')])
        async def select(request,destination,candidates,settings):
            assert {r['id'] for r in candidates}=={'mall','meal'}
            return ['mall','meal']
        try:
            result=await create_plan(c,PlanRequest(date='2026-11-01',district='Central and Western',interests=['mall']),select)
            assert {p['id'] for p in result['map_places']}=={'mall','meal','parking:1'}
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())


def test_snapshot_change_during_parking_read_cannot_poison_new_revision_cache():
    async def run():
        c=container();original=c.parking.list;first=True
        old=c.pets.places()['items'];new=[{**p,'id':'meal2'} if p['id']=='meal' else p for p in old]
        async def parking(**kwargs):
            nonlocal first
            if first:
                first=False;c.pets.revision='v2';c.pets.places=lambda **kwargs:{'items':new}
            return await original(**kwargs)
        c.parking.list=parking
        async def select(request,destination,candidates,settings):return [r['id'] for r in candidates]
        try:
            request=PlanRequest(date='2026-11-01',interests=['mall'])
            await create_plan(c,request,select)
            current=await create_plan(c,request,select)
            assert 'meal2' in {p['id'] for p in current['map_places']}
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())


def test_random_area_is_drawn_again_even_on_candidate_cache_hit(monkeypatch):
    choices=[]
    def choose(items):
        choices.append(len(items));return items[0] if len(choices)==1 else items[-1]
    monkeypatch.setattr('backend.app.services.outing_plan.secrets.choice',choose)
    async def run():
        c=container();c.pets.places()['items'].append(place('curated:mall:stanley-plaza-stanley-plaza','malls'))
        async def select(*args):return ['mall','meal']
        try:
            request=PlanRequest(date='2026-11-01',region='hong_kong_island',interests=['mall'],random=True)
            one=await create_plan(c,request,select);two=await create_plan(c,request,select)
            assert len(choices)==2 and choices[0]>=2
            assert one['destination']['id']!=two['destination']['id']
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())


def test_explicit_meal_only_plan_does_not_add_a_park_or_mall():
    async def run():
        c=container()
        async def select(request,destination,candidates,settings):
            assert {r['purpose'] for r in candidates}=={'meal'}
            return [candidates[0]['id']]
        try:
            result=await create_plan(c,PlanRequest(date='2026-11-01',interests=[]),select)
            assert [s['purpose'] for g in result['parking_groups'] for s in g['stops']]==['meal']
        finally:await c.plan_candidates.aclose()
    asyncio.run(run())
