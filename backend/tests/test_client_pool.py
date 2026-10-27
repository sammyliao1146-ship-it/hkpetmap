import asyncio
from types import SimpleNamespace
from agent import client_pool


class FakeClient:
    closed = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def with_options(self, **kwargs):
        return SimpleNamespace(base=self, **kwargs)

    async def close(self):
        FakeClient.closed += 1


def test_clients_are_reused_and_expire(monkeypatch):
    monkeypatch.setattr(client_pool, 'AsyncOpenAI', FakeClient)
    client_pool._pool.clear()

    async def run():
        a = client_pool.get_client('k', 'https://x', 5)
        b = client_pool.get_client('k', 'https://x', 9)
        assert a.base is b.base and (a.timeout, b.timeout) == (5, 9)
        other = client_pool.get_client('k2', 'https://x', 5)
        assert other.base is not a.base
        key = client_pool._key('k', 'https://x')
        client_pool._pool[key][2] -= 1000
        fresh = client_pool.get_client('k', 'https://x', 5)
        await asyncio.sleep(0)
        assert fresh.base is not a.base and FakeClient.closed == 1

    asyncio.run(run())
    client_pool._pool.clear()
