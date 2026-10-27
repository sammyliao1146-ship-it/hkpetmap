from fastapi.testclient import TestClient
from agent.subagents.intent_router import IntentDecision
from backend.app.config.settings import Settings
from backend.app.config.container import Container
from test_pet_data import service
from main import app


def test_chat_origin_reaches_search_without_leaking_into_next_request(tmp_path,monkeypatch):
    svc,cache,client=service(tmp_path)
    svc.snapshot.places[0].latitude=22.3;svc.snapshot.places[0].longitude=114.17
    app.state.container=Container(Settings(api_key='unit-test',model='test',base_url='https://example.invalid',cors_origins=[]),cache,client,svc)
    captured=[]
    async def ensure():pass
    async def classify(*a,**kw):return IntentDecision(intent='map_query',map_mode='distance',confidence=.99)
    async def answer(message,**kwargs):
        result=await kwargs['access'].search_places(sort_by='distance');captured.append(result)
        return result['query_status']
    async def approve(**kwargs):return True
    monkeypatch.setattr(svc,'ensure',ensure)
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent',classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant',answer)
    monkeypatch.setattr('backend.app.routers.assistant.review_answer',approve)
    try:
        with TestClient(app) as api:
            r=api.post('/api/v1/assistant/chat',json={'message':'附近公園','origin':{'latitude':22.3,'longitude':114.17}})
            assert r.status_code==200 and r.json()['answer']=='ready'
            assert captured[0]['items'][0]['distance_m']==0
            assert api.post('/api/v1/assistant/chat',json={'message':'附近公園'}).json()['answer']=='needs_location'
            assert captured[1]['origin'] is None
            assert api.post('/api/v1/assistant/chat',json={'message':'附近','origin':{'latitude':91,'longitude':114}}).status_code==422
    finally:del app.state.container
