"""Dedicated public-data worker. Google collection scripts are never imported."""
import argparse,asyncio,json,logging
from backend.app.config.container import build_container
from backend.app.config.settings import get_settings
from backend.app.services.snapshot_sync import run_sync

async def serve(*,once=False,mode='redis',interval=None):
    container=await build_container(get_settings())
    try:
        while True:
            try:
                result=await run_sync(container.pets,mode=mode)
                print(json.dumps(result,ensure_ascii=False),flush=True)
            except Exception:
                if once:raise
                logging.getLogger(__name__).exception('Public data sync failed; snapshots remain available')
            if once:return
            await asyncio.sleep(interval or container.settings.sync_check_seconds)
    finally:
        await container.aclose()

def main():
    settings=get_settings();parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true',help='Check freshness once; suitable for a platform scheduled job')
    parser.add_argument('--lock',choices=['redis','file'],default='redis',help='Redis for multiple hosts; file only for one host/shared disk')
    parser.add_argument('--interval',type=float,default=settings.sync_check_seconds,help='Seconds between freshness checks (default 600)')
    args=parser.parse_args()
    if args.interval<=0:parser.error('--interval must be positive')
    asyncio.run(serve(once=args.once,mode=args.lock,interval=args.interval))
if __name__=='__main__':main()
