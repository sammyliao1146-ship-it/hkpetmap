"""Refresh public pet data and optionally resolve missing addresses using government ALS."""
import argparse
import asyncio
from backend.app.config.container import build_container
from backend.app.config.settings import get_settings
from backend.app.services.snapshot_sync import run_sync

async def main(geocode,mode='redis'):
    c=await build_container(get_settings())
    try:
        result=await run_sync(c.pets,mode=mode,force=True,geocode=geocode)
        if result['status']=='locked':
            print(result);return
        data=c.pets.places()
        print({"total":data["total"],"mapped":data["mapped"],"activities":c.pets.activities()["total"],"sources":data["sources"]})
    finally:
        await c.aclose()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--geocode",action="store_true")
    parser.add_argument('--lock',choices=['redis','file'],default='redis')
    args=parser.parse_args()
    asyncio.run(main(args.geocode,args.lock))
