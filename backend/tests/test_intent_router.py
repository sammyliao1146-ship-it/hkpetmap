import asyncio
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from agent.subagents.intent_router import IntentDecision, route_action
from backend.app.config.settings import Settings
from backend.app.config.container import Container
from test_pet_data import service
from main import app

@pytest.mark.parametrize('intent,mode',[('map_query','distance'),('map_query','rating'),('map_query','cuisine'),('map_query','random'),('trip_plan','none'),('transport','none'),('pet_policy','none')])
def test_threshold_boundary(intent,mode):
    assert route_action(IntentDecision(intent=intent,map_mode=mode,confidence=.75))=='main_agent'
    assert route_action(IntentDecision(intent=intent,map_mode=mode,confidence=.749))=='clarify'

def test_schema_and_refusal():
    assert route_action(IntentDecision(intent='out_of_scope',map_mode='none',confidence=.99))=='refuse'
    assert route_action(IntentDecision(intent='out_of_scope',map_mode='none',confidence=.4))=='clarify'
    for payload in [dict(intent='unknown',map_mode='none',confidence=.99),dict(intent='map_query',map_mode='none',confidence=.9),dict(intent='transport',map_mode='rating',confidence=.9),dict(intent='map_query',map_mode='general',confidence=1.1),dict(intent='map_query',map_mode='general',confidence=float('nan'))]:
        with pytest.raises(ValidationError): IntentDecision(**payload)
    with pytest.raises(ValueError): Settings(api_key='',model='test',base_url='https://example.invalid',cors_origins=[],intent_confidence_threshold=0)

@pytest.mark.parametrize('intent,confidence,action',[('map_query',.99,'main_agent'),('trip_plan',.9,'main_agent'),('transport',.9,'main_agent'),('pet_policy',.9,'main_agent'),('out_of_scope',.99,'refuse'),('map_query',.6,'clarify'),('out_of_scope',.6,'clarify')])
def test_api_routes_before_main_and_preserves_context(tmp_path,monkeypatch,intent,confidence,action):
    svc,cache,client=service(tmp_path)
    app.state.container=Container(Settings(api_key='unit-test-no-network',model='main-test',base_url='https://example.invalid/v1',cors_origins=[],intent_model='small-test'),cache,client,svc)
    captured=[];main_calls=[]
    async def ensure():pass
    async def classify(message,**kwargs):
        captured.append((message,kwargs))
        return IntentDecision(intent=intent,map_mode='rating' if intent=='map_query' else 'none',confidence=confidence)
    async def main(message,**kwargs):main_calls.append(kwargs);return 'Main answer'
    async def approve(**kwargs):return True
    monkeypatch.setattr(svc,'ensure',ensure)
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent',classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant',main)
    monkeypatch.setattr('backend.app.routers.assistant.review_answer',approve)
    history=[{'role':'user','content':'Find a pet friendly cafe'}]
    try:
        with TestClient(app) as api:
            r=api.post('/api/v1/assistant/chat',json={'message':'Near me','language':'en','history':history})
            assert r.status_code==200
            d=r.json();assert d['routing']['action']==action and d['routing']['classifier_model']=='small-test'
            assert captured[0][1]['history']==history
            if action=='main_agent':
                assert len(main_calls)==1 and main_calls[0]['intent'].intent==intent
                assert main_calls[0]['history']==history and main_calls[0]['language']=='en'
                assert d['answer']=='Main answer' and d['model']=='main-test'
            else:
                assert main_calls==[] and d['model']=='small-test' and d['answer']!='Main answer'
    finally: del app.state.container

@pytest.mark.parametrize('error',[TimeoutError,ValueError])
def test_classifier_failure_never_calls_main(tmp_path,monkeypatch,error):
    svc,cache,client=service(tmp_path)
    app.state.container=Container(Settings(api_key='unit-test-no-network',model='test',base_url='https://example.invalid',cors_origins=[]),cache,client,svc)
    async def ensure():pass
    async def classify(*a,**kw):raise error('classifier failed')
    async def forbidden(*a,**kw):raise AssertionError('Main must not run')
    monkeypatch.setattr(svc,'ensure',ensure)
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent',classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant',forbidden)
    try:
        with TestClient(app) as api:
            assert api.post('/api/v1/assistant/chat',json={'message':'搵餐廳'}).status_code==503
    finally:del app.state.container
