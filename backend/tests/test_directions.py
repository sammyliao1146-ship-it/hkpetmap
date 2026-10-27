import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from agent.data.data_access import PetDataAccess
from agent.subagents.intent_router import IntentDecision
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from main import app
from test_pet_data import service


def test_directions_use_saved_venue_and_shared_origin_without_transit(tmp_path):
    svc, cache, client = service(tmp_path)
    restaurant = svc.snapshot.places[1]
    restaurant.latitude, restaurant.longitude = 22.3, 114.17
    access = PetDataAccess(svc, origin=(22.31, 114.18))
    result = asyncio.run(access.directions(restaurant.id))
    assert result['status'] == 'ready'
    assert {link['mode'] for link in result['directions']} == {'walking', 'driving'}
    for link in result['directions']:
        params = parse_qs(urlparse(link['url']).query)
        assert params['destination'] == ['22.3,114.17']
        assert params['origin'] == ['22.31,114.18']
        assert link['url'] in [s['url'] for s in access.direction_sources]
    rules = {r['mode']: r['pet_access'] for r in result['restrictions']}
    assert rules['mtr_heavy_rail'] == 'not_permitted'
    assert rules['public_light_bus'] == 'operator_confirmation_required'
    assert asyncio.run(access.directions('missing'))['status'] == 'needs_destination'


def test_directions_fall_back_to_saved_address_and_never_guess_origin(tmp_path):
    svc, cache, client = service(tmp_path)
    access = PetDataAccess(svc)
    restaurant = svc.snapshot.places[1]
    assert asyncio.run(access.directions(restaurant.id))['status'] == 'missing_destination_details'
    restaurant.address = '1 Example Road'
    result = asyncio.run(access.directions(restaurant.id))
    for link in result['directions']:
        params = parse_qs(urlparse(link['url']).query)
        assert params['destination'] == ['餐廳 1 Example Road']
        assert 'origin' not in params


def test_transport_followup_keeps_client_context_after_memory_expiry_and_returns_sources(tmp_path, monkeypatch):
    svc, cache, client = service(tmp_path)
    svc.snapshot.places[1].address = '1 Example Road'
    settings = Settings(api_key='test', model='test', base_url='https://example.invalid', cors_origins=[])
    app.state.container = Container(settings, cache, client, svc)
    history = [{'role':'assistant', 'content':'Try the restaurant at 1 Example Road.'}]

    async def classify(message, **kwargs):
        assert kwargs['history'] == history
        return IntentDecision(intent='transport', map_mode='none', confidence=.99)

    async def answer(message, **kwargs):
        result = await kwargs['access'].directions('restaurant:1')
        return '餐廳: ' + result['directions'][0]['url']

    async def review(**kwargs):
        assert any('google.com/maps/dir/' in s['url'] for s in kwargs['sources'])
        return True

    monkeypatch.setattr('backend.app.routers.assistant.classify_intent', classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant', answer)
    monkeypatch.setattr('backend.app.routers.assistant.review_answer', review)
    try:
        with TestClient(app) as api:
            result = api.post('/api/v1/assistant/chat', json={
                'message':'how to go to the restaurant', 'language':'en',
                'session_id':'expired-session', 'history':history,
            })
            assert result.status_code == 200
            assert result.json()['sources']
            assert result.json()['places'][0]['id'] == 'restaurant:1'
    finally:
        del app.state.container
