import asyncio,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import httpx,pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from backend.app.cache.redis_cache import RedisCache
from backend.app.models.pet import Snapshot
from backend.app.services.pet_service import PetService
from backend.app.services.snapshot_sync import run_sync,SyncLockUnavailable
from backend.app.config.lifespan import lifespan

NOW=datetime.now(timezone.utc)
def payload(name,published):
    return Snapshot(fetched_at=NOW-timedelta(days=2),published_at=published,places=[{'id':'parks:test','category':'parks','name':name,'source_url':'https://example.com','source_name':'Test'}],activities=[],sources=[])


def test_web_lifespan_only_reads_snapshots_and_never_syncs():
    async def run():
        reads=[];closed=[]
        class Pets:
            async def reload_if_changed(self):reads.append(True)
            async def ensure(self):raise AssertionError('Web called ensure')
            async def refresh(self,**kwargs):raise AssertionError('Web fetched upstream')
        async def close():closed.append(True)
        app=SimpleNamespace(state=SimpleNamespace(container=SimpleNamespace(pets=Pets(),settings=SimpleNamespace(snapshot_poll_seconds=.001),aclose=close)))
        async with lifespan(app):await asyncio.sleep(.01)
        assert reads and closed==[True]
    asyncio.run(run())


def test_reader_sees_new_local_publication_even_if_fetch_time_unchanged(tmp_path):
    async def run():
        calls=[]
        async def reject(request):calls.append(str(request.url));raise AssertionError('Reader contacted upstream')
        client=httpx.AsyncClient(transport=httpx.MockTransport(reject));cache=RedisCache(None,'read-test');path=tmp_path/'snapshot.json'
        old=payload('old',NOW-timedelta(hours=1));new=payload('new',NOW)
        path.write_text(old.model_dump_json());await cache.set_json('snapshot:v1',old.model_dump(mode='json'))
        svc=PetService(cache,client,path)
        await svc.load();assert next(p for p in svc.snapshot.places if p.id=='parks:test').name=='old'
        temporary=path.with_suffix('.tmp');temporary.write_text(new.model_dump_json());temporary.replace(path)
        await svc.ensure()
        assert next(p for p in svc.snapshot.places if p.id=='parks:test').name=='new'
        assert svc.snapshot.fetched_at==old.fetched_at and svc.snapshot.published_at==NOW
        assert not calls
        await client.aclose();await cache.aclose()
    asyncio.run(run())


class FakePets:
    def __init__(self,path,cache=None):
        self.snapshot_path=path;self.cache=cache;self.snapshot=SimpleNamespace(fetched_at=NOW)
        self.loads=0;self.refreshes=0;self.due=True;self.started=asyncio.Event();self.finish=asyncio.Event();self.cancelled=False
    async def load(self):self.loads+=1
    def refresh_due(self):return self.due
    async def refresh(self,**kwargs):
        self.refreshes+=1;self.started.set()
        try:await self.finish.wait()
        except asyncio.CancelledError:self.cancelled=True;raise
        await kwargs['before_publish']();self.due=False


def test_two_workers_and_manual_command_cannot_overlap_on_shared_disk(tmp_path):
    async def run():
        first=FakePets(tmp_path/'snapshot.json');second=FakePets(first.snapshot_path)
        task=asyncio.create_task(run_sync(first,mode='file'))
        await first.started.wait()
        assert await run_sync(second,mode='file',force=True,activities_only=True)=={'status':'locked'}
        assert second.loads==0 and second.refreshes==0
        first.finish.set();assert (await task)['status']=='updated'
        assert await run_sync(first,mode='file')=={'status':'fresh'}
        assert first.refreshes==1
    asyncio.run(run())


def test_parking_refresh_is_exclusive_and_runs_even_when_pet_snapshot_is_fresh(tmp_path):
    async def run():
        first=FakePets(tmp_path/'snapshot.json');first.due=False
        second=FakePets(first.snapshot_path);second.due=False
        started=asyncio.Event();release=asyncio.Event();calls=[]
        async def parking():
            calls.append(True);started.set();await release.wait()
        job=asyncio.create_task(run_sync(first,mode='file',parking=SimpleNamespace(list=parking)))
        await started.wait()
        assert await run_sync(second,mode='file',parking=SimpleNamespace(list=parking))=={'status':'locked'}
        assert calls==[True]
        release.set();assert await job=={'status':'fresh'}
        assert first.refreshes==second.refreshes==0
    asyncio.run(run())


def test_redis_lock_failure_is_fail_closed(tmp_path):
    async def run():
        class Lock:
            async def acquire(self):raise RedisConnectionError('unavailable')
        cache=SimpleNamespace(client=SimpleNamespace(lock=lambda *a,**kw:Lock()),_key=lambda s:s)
        pets=FakePets(tmp_path/'snapshot.json',cache)
        with pytest.raises(SyncLockUnavailable):await run_sync(pets)
        assert pets.loads==0 and pets.refreshes==0
    asyncio.run(run())


def test_lease_renewal_failure_cancels_work_and_releases_lock(tmp_path,monkeypatch):
    async def run():
        class Lock:
            released=False
            async def acquire(self):return True
            async def extend(self,*a,**kw):raise RedisConnectionError('lost connection')
            async def owned(self):return True
            async def release(self):self.released=True
        lock=Lock();cache=SimpleNamespace(client=SimpleNamespace(lock=lambda *a,**kw:lock),_key=lambda s:s)
        pets=FakePets(tmp_path/'snapshot.json',cache)
        monkeypatch.setattr('backend.app.services.snapshot_sync.LEASE_SECONDS',.03)
        with pytest.raises(RedisConnectionError):await run_sync(pets)
        assert pets.cancelled and lock.released
    asyncio.run(run())


def test_snapshot_and_revision_are_published_together_in_shared_redis():
    import fakeredis.aioredis
    async def run():
        client=fakeredis.aioredis.FakeRedis();cache=RedisCache(client,'test-publish')
        data=payload('new',NOW).model_dump(mode='json')
        await cache.publish_snapshot(data,'revision-2',3600,require_shared=True)
        assert await cache.get_json('snapshot:v1')==data
        assert await cache.get_bytes('snapshot:revision')==b'revision-2'
        await cache.aclose()
    asyncio.run(run())


def test_public_sync_worker_does_not_call_google(tmp_path):
    async def run():
        hosts=[]
        async def upstream(request):
            hosts.append(request.url.host)
            assert request.url.host!='places.googleapis.com'
            return httpx.Response(503)
        client=httpx.AsyncClient(transport=httpx.MockTransport(upstream));cache=RedisCache(None,'public-worker-test')
        path=tmp_path/'snapshot.json';path.write_text(payload('kept',NOW-timedelta(hours=1)).model_dump_json())
        svc=PetService(cache,client,path)
        try:
            assert (await run_sync(svc,mode='file',force=True))['status']=='updated'
            assert hosts and 'places.googleapis.com' not in hosts
            assert next(p for p in svc.snapshot.places if p.id=='parks:test').name=='kept'
        finally:
            await client.aclose();await cache.aclose()
    asyncio.run(run())
