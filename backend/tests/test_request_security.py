import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config.middleware import register_middleware
from backend.app.config.request_security import is_secret_probe
from backend.app.config.settings import Settings

CASES = json.loads(Path(__file__).with_name('secret-probes.json').read_text())


@pytest.mark.parametrize('path', CASES['blocked'])
def test_secret_probe_recognised(path):
    assert is_secret_probe(path)


@pytest.mark.parametrize('path', CASES['allowed'])
def test_normal_paths_allowed(path):
    assert not is_secret_probe(path)


def test_direct_origin_probe_never_reaches_route():
    app = FastAPI()
    register_middleware(app, Settings(api_key='', model='test', base_url='https://example.invalid', cors_origins=[]), '/api/v1')
    reached = []

    @app.api_route('/{path:path}', methods=['GET', 'POST', 'HEAD'])
    async def downstream(path: str):
        reached.append(path)
        return {'ok':True}

    with TestClient(app) as client:
        for method in ('GET', 'POST', 'HEAD'):
            for path in CASES['blocked']:
                response = client.request(method, path)
                assert response.status_code == 404
                assert response.headers['cache-control'] == 'private, no-store'
        assert not reached
        assert client.get('/api/v1/catalog?q=.env').status_code == 200
        assert client.get('/.well-known/security.txt').status_code == 200
        assert len(reached) == 2
