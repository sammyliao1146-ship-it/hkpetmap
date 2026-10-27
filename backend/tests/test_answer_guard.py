import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from agent.subagents.answer_guard import AnswerReview, blocked_reply, review_answer
from agent.subagents.intent_router import IntentDecision
from agent.subagents.web_knowledge import WebKnowledgeService
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from main import app
from test_pet_data import service


def test_structured_answer_reviewer_approves_only_all_positive_fields(monkeypatch):
    verdicts = [
        AnswerReview(relevant=True, within_requested_scope=True, addresses_current_request=True),
        AnswerReview(relevant=False, within_requested_scope=True, addresses_current_request=False),
        None,
    ]
    captured = []

    class Responses:
        async def parse(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(output_parsed=verdicts.pop(0))

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

        def with_options(self, **kwargs):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr('agent.assembly.client_pool.AsyncOpenAI', Client)
    args = dict(query='狗狗可以食意粉嗎', answer='純意粉的資料', intent='pet_health', map_mode='none',
                api_key='test', base_url='https://example.invalid', model='small', timeout_seconds=2)
    assert asyncio.run(review_answer(**args)) is True
    assert asyncio.run(review_answer(**args)) is False
    assert asyncio.run(review_answer(**args)) is False
    assert captured[0]['store'] is False and captured[0]['text_format'] is AnswerReview


def test_answer_reviewer_fails_closed_on_provider_error(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(parse=self.parse)

        async def parse(self, **kwargs):
            raise TimeoutError('review timed out')

        def with_options(self, **kwargs):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr('agent.assembly.client_pool.AsyncOpenAI', Client)
    approved = asyncio.run(review_answer(query='狗狗疫苗', answer='回答', intent='pet_health', map_mode='none',
        api_key='test', base_url='https://example.invalid', model='small', timeout_seconds=1))
    assert approved is False
    assert '切題' in blocked_reply('zh-Hant')


def test_multiple_research_turns_filter_irrelevant_answer_and_preserve_relevant_ones(monkeypatch):
    cases = [
        ('狗狗能吃意粉嗎', 'pet_health', 'https://spca.org.hk/vet-services/', 'Relevant: plain pasta'),
        ('餐廳菜單有什麼', 'restaurant_info', 'https://www.openrice.com/', 'Relevant: menu details'),
        ('狗可以進餐廳嗎', 'pet_policy', 'https://www.pets.gov.hk/', 'Relevant: access rules'),
        ('狗狗搭港鐵有什麼限制', 'transport', 'https://www.mtr.com.hk/', 'Relevant: pet transport policy'),
        ('狗狗打疫苗', 'pet_health', 'https://www.spca.org.hk/vet-services/', 'OFF_TOPIC: stock market outlook'),
        ('Tell me how to day trade', 'out_of_scope', None, 'Should never be searched'),
    ]
    seen = []

    async def run(agent, payload, **kwargs):
        request = __import__('json').loads(payload)
        case = next(x for x in cases if x[0] == request['question'])
        seen.append(case[0])
        if not case[2]:
            raise AssertionError('out-of-scope request reached web search')
        url = case[2]
        result = SimpleNamespace(
            raw_responses=[SimpleNamespace(output=[
                {'type':'web_search_call','status':'completed','action':{'sources':[{'url':url,'title':'Topic source'}]}},
                {'type':'message','content':[{'annotations':[{'type':'url_citation','url':url,'title':'Topic source'}]}]},
            ])],
            final_output=case[3],
        )
        return result

    async def review(**kwargs):
        return 'OFF_TOPIC' not in kwargs['answer']

    monkeypatch.setattr('agent.subagents.web_knowledge.Runner.run', run)
    monkeypatch.setattr('agent.subagents.web_knowledge.review_answer', review)
    settings = Settings(api_key='test', model='main', base_url='https://example.invalid', cors_origins=[])
    svc = WebKnowledgeService(settings)
    results = []
    history = []
    for query, intent, _, _ in cases:
        decision = IntentDecision(intent=intent, map_mode='none', confidence=.99)
        result = asyncio.run(svc.search(query, history=history, decision=decision))
        results.append(result)
        history.extend([{'role':'user','content':query},{'role':'assistant','content':result['answer']}])

    assert [r['status'] for r in results] == ['ok','ok','ok','ok','filtered','refuse']
    assert 'stock market' not in results[4]['answer'] and results[4]['sources'] == []
    assert seen == [c[0] for c in cases[:-1]]


def test_main_agent_answer_is_checked_before_api_returns_it(tmp_path, monkeypatch):
    svc, cache, client = service(tmp_path)
    settings = Settings(api_key='test', model='main', base_url='https://example.invalid', cors_origins=[])
    app.state.container = Container(settings, cache, client, svc)

    async def ensure():
        return None

    async def classify(*args, **kwargs):
        return IntentDecision(intent='trip_plan', map_mode='none', confidence=.98)

    async def unrelated(*args, **kwargs):
        return 'Unrelated financial market answer.'

    async def reject(**kwargs):
        assert kwargs['intent'] == 'trip_plan'
        assert 'restaurant' in kwargs['query']
        return False

    monkeypatch.setattr(svc, 'ensure', ensure)
    monkeypatch.setattr('backend.app.routers.assistant.classify_intent', classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant', unrelated)
    monkeypatch.setattr('backend.app.routers.assistant.review_answer', reject)
    try:
        with TestClient(app) as api:
            response = api.post('/api/v1/assistant/chat', json={'message':'Find a dog-friendly restaurant'})
            assert response.status_code == 200
            assert 'financial market' not in response.json()['answer']
            assert '切題答案' in response.json()['answer']
            assert response.json()['sources'] == []
    finally:
        del app.state.container
