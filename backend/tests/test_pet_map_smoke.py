"""End-to-end smoke coverage for Pet Map HTTP and multi-turn chat flows."""

from fastapi.testclient import TestClient

from agent.assembly.intent_router import IntentDecision
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from backend.app.models.pet import Place
from main import app
from test_pet_data import service


SOURCE_URL = 'https://www.pets.gov.hk/'


def _place(place_id, category, name, district, latitude, longitude):
    return Place(
        id=place_id,
        category=category,
        name=name,
        district=district,
        address=f'{district}測試地址',
        latitude=latitude,
        longitude=longitude,
        coordinate_source='test fixture',
        source_url=SOURCE_URL,
        source_name='Pet Map smoke fixture',
    )


def _add_map_fixtures(svc):
    svc.snapshot.places.extend([
        _place('pet-park:saikung', 'pet_parks', '西貢海濱寵物公園', '西貢區', 22.382, 114.271),
        _place('pet-park:kowloon', 'pet_parks', '九龍城寵物公園', '九龍城區', 22.329, 114.189),
        _place('vet:saikung', 'vets', '西貢動物醫院', '西貢區', 22.381, 114.270),
    ])


def _install_test_container(tmp_path, monkeypatch):
    svc, cache, client = service(tmp_path)
    _add_map_fixtures(svc)
    settings = Settings(
        api_key='unit-test', model='test-model', base_url='https://example.invalid/v1',
        cors_origins=[], cache_prefix='pet-map-smoke',
    )
    app.state.container = Container(settings, cache, client, svc)

    async def no_refresh():
        return None

    monkeypatch.setattr(svc, 'ensure', no_refresh)
    return svc


def test_pet_map_http_smoke_filters_details_and_activities(tmp_path, monkeypatch):
    _install_test_container(tmp_path, monkeypatch)
    try:
        with TestClient(app) as api:
            assert api.get('/api/v1/health').json()['status'] == 'ok'

            catalog = api.get('/api/v1/catalog')
            assert catalog.status_code == 200
            assert {item['key'] for item in catalog.json()['categories']} >= {'pet_parks', 'vets'}

            parks = api.get('/api/v1/places', params={
                'mode': 'facilities', 'category': 'pet_parks', 'district': '西貢區',
            })
            assert parks.status_code == 200
            assert parks.json()['total'] == 1
            assert parks.json()['mapped'] == 1
            assert parks.json()['items'][0]['id'] == 'pet-park:saikung'

            detail = api.get('/api/v1/places/pet-park:saikung')
            assert detail.status_code == 200
            assert detail.json()['items'][0]['name'] == '西貢海濱寵物公園'

            vets = api.get('/api/v1/places', params={'category': 'vets', 'q': '動物醫院'})
            assert vets.status_code == 200
            assert vets.json()['items'][0]['id'] == 'vet:saikung'

            activities = api.get('/api/v1/activities', params={'q': '幼犬社交班'})
            assert activities.status_code == 200
            assert activities.json()['items'][0]['id'] == 'course:1'
    finally:
        del app.state.container


def test_pet_map_chat_smoke_preserves_context_for_three_turns(tmp_path, monkeypatch):
    svc = _install_test_container(tmp_path, monkeypatch)
    classifier_calls = []
    agent_calls = []

    async def classify(message, **kwargs):
        classifier_calls.append((message, kwargs['history']))
        return IntentDecision(intent='map_query', map_mode='general', confidence=.99)

    async def answer(message, **kwargs):
        history = kwargs['history']
        access = kwargs['access']
        agent_calls.append((message, history))
        if message == '搵寵物公園':
            result = await access.search_places(category='pet_parks')
        elif message == '西貢區呢':
            assert history[-2]['content'] == '搵寵物公園'
            result = await access.search_places(category='pet_parks', district='西貢區')
        else:
            # The follow-up uses the district requested on the previous turn.
            assert message == '獸醫呢'
            assert any(m['role'] == 'user' and m['content'] == '西貢區呢' for m in history)
            result = await access.search_places(category='vets', district='西貢區')
        assert result['query_status'] == 'ready'
        selected = result['items'][0]
        return f"搵到：{selected['name']}（{len(history)} 條歷史訊息）"

    monkeypatch.setattr('backend.app.routers.assistant.classify_intent', classify)
    monkeypatch.setattr('backend.app.routers.assistant.run_pet_assistant', answer)
    session_id = 'pet-map-smoke-01'
    turns = ['搵寵物公園', '西貢區呢', '獸醫呢']

    try:
        with TestClient(app) as api:
            responses = [api.post('/api/v1/assistant/chat', json={
                'message': message, 'session_id': session_id,
            }) for message in turns]

        assert [response.status_code for response in responses] == [200, 200, 200]
        answers = [response.json() for response in responses]
        assert answers[0]['places'] == [{'id': 'park:1', 'name': '寵物公園'}]
        assert answers[1]['places'] == [{'id': 'pet-park:saikung', 'name': '西貢海濱寵物公園'}]
        assert answers[2]['places'] == [{'id': 'vet:saikung', 'name': '西貢動物醫院'}]

        expected_histories = [
            [],
            [{'role': 'user', 'content': turns[0]},
             {'role': 'assistant', 'content': answers[0]['answer']}],
            [{'role': 'user', 'content': turns[0]},
             {'role': 'assistant', 'content': answers[0]['answer']},
             {'role': 'user', 'content': turns[1]},
             {'role': 'assistant', 'content': answers[1]['answer']}],
        ]
        assert [history for _, history in classifier_calls] == expected_histories
        assert [history for _, history in agent_calls] == expected_histories
        assert [message for message, _ in classifier_calls] == turns
        assert [message for message, _ in agent_calls] == turns
    finally:
        del app.state.container
