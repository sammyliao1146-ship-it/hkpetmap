"""Refresh only public activity sources; preserve restaurant/facility data."""
import argparse
import asyncio
from backend.app.config.container import build_container
from backend.app.config.settings import get_settings
from backend.app.services.snapshot_sync import run_sync

async def main(mode='redis'):
    container = await build_container(get_settings())
    try:
        result=await run_sync(container.pets,mode=mode,force=True,activities_only=True)
        if result['status']=='locked':
            print(result);return
        print({'activities': container.pets.activities()['total'],
               'sources': [s for s in container.pets.snapshot.sources if s['key'].startswith('activities')]})
    finally:
        await container.aclose()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock',choices=['redis','file'],default='redis')
    asyncio.run(main(parser.parse_args().lock))
