"""Exclusive public-data sync, shared by the worker and manual commands."""
import asyncio
import logging
from contextlib import asynccontextmanager
from redis.exceptions import LockError,RedisError

log=logging.getLogger(__name__)
LEASE_SECONDS=180

class SyncLockUnavailable(RuntimeError):pass

@asynccontextmanager
async def sync_lease(pets,mode='redis'):
    if mode=='file':
        import fcntl
        path=pets.snapshot_path.with_suffix('.sync.lock');path.parent.mkdir(parents=True,exist_ok=True)
        handle=path.open('a')
        try:
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                yield None;return
            yield handle
        finally:
            handle.close()
        return
    if mode!='redis':raise ValueError('lock mode must be redis or file')
    if pets.cache.client is None:raise SyncLockUnavailable('Redis is required; use --lock file only for a single host with shared storage')
    lock=pets.cache.client.lock(pets.cache._key('sync:public-data'),timeout=LEASE_SECONDS,blocking=False,thread_local=False)
    try:
        acquired=await lock.acquire()
    except (RedisError,OSError) as exc:
        raise SyncLockUnavailable('Redis sync lock unavailable; no upstream requests made') from exc
    if not acquired:
        yield None;return
    try:
        yield lock
    finally:
        try:await lock.release()
        except (RedisError,OSError,LockError):log.warning('Could not release sync lease; token ownership/expiry prevents deleting another worker lock')

async def run_sync(pets,*,mode='redis',force=False,geocode=False,activities_only=False,parking=None):
    """Return skipped when another task owns the lease or data is still fresh."""
    async with sync_lease(pets,mode) as lease:
        if lease is None:return {'status':'locked'}
        async def guard():
            if mode=='redis' and not await lease.owned():
                raise SyncLockUnavailable('Sync lease lost; refusing snapshot publication')
        async def work():
            # Reload *inside* the lease so a second worker sees the first one's publication.
            await pets.load()
            # The dedicated job also refreshes parking under the same exclusive lease.
            # Planning reads the published cache and never waits for this upstream I/O.
            if parking is not None:
                await guard()
                await parking.list()
            if not force and not pets.refresh_due():return {'status':'fresh'}
            await pets.refresh(force=force,geocode=geocode,activities_only=activities_only,
                               before_publish=guard,require_shared=(mode=='redis'))
            return {'status':'updated','fetched_at':pets.snapshot.fetched_at.isoformat()}
        if mode=='file':return await work()
        async def renew():
            while True:
                await asyncio.sleep(LEASE_SECONDS/3)
                if not await lease.extend(LEASE_SECONDS,replace_ttl=True):raise SyncLockUnavailable('Sync lease renewal failed')
        job=asyncio.create_task(work(),name='public-data-sync')
        heartbeat=asyncio.create_task(renew(),name='sync-lease-renewal')
        try:
            done,_=await asyncio.wait((job,heartbeat),return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                await heartbeat
                raise SyncLockUnavailable('Sync heartbeat stopped unexpectedly')
            return await job
        finally:
            job.cancel();heartbeat.cancel()
            await asyncio.gather(job,heartbeat,return_exceptions=True)
