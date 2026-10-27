"""Sync official LCSD photographs. Run after sync_data: python -m scripts.sync_photos."""
import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.config.container import build_container
from backend.app.config.settings import get_settings
from backend.app.data.photos import MANIFEST, FACILITY_TYPES, attach_photos, district_id, name_key, parse_lcsd_photos

async def main():
    container=await build_container(get_settings())
    try:
        snapshot=container.pets.snapshot
        if snapshot is None:
            raise SystemExit('請先執行 python -m scripts.sync_data。')
        try:
            previous=json.loads(MANIFEST.read_text())
        except (OSError,ValueError):
            previous={'places':{},'pages':{}}
        output=previous.get('places',{}).copy()
        statuses=previous.get('pages',{}).copy()
        semaphore=asyncio.Semaphore(4)
        jobs={}
        for p in snapshot.places:
            did=district_id(p.district)
            ftid=FACILITY_TYPES.get(p.category)
            if did and ftid:
                jobs.setdefault((ftid,did),[]).append(p)
        async def fetch(key,places):
            ftid,did=key
            url=f'https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do?ftid={ftid}&fcid=&did={did}'
            async with semaphore:
                try:
                    r=await container.client.get(url);r.raise_for_status()
                    found=parse_lcsd_photos(r.text,url)
                    # An unexpected error page must not erase valid photo matches.
                    if 'fac-table' not in r.text:
                        raise ValueError('Unexpected facility page')
                    for p in places:
                        photos=found.get(name_key(p.name),[])
                        output[p.id]=[{**photo,'alt':p.name+'・場地實景'} for photo in photos]
                    statuses[url]={'status':'ready','checked_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat()}
                except Exception as exc:
                    statuses[url]={'status':'stale','error':type(exc).__name__}
                    logging.warning('Photo page unavailable: %s',url)
                finally:
                    await asyncio.sleep(.15)
        await asyncio.gather(*(fetch(k,v) for k,v in jobs.items()))
        # Venue-specific official centre images, never generic page banners or logos.
        official={
            'curated:spca-wan-chai':[{'url':'https://www.spca.org.hk/wp-content/uploads/2023/06/Wan-Chai-3-1.jpg','source_url':'https://www.spca.org.hk/about-us/spca-centres/','credit':'香港愛護動物協會 SPCA','alt':'愛護動物協會灣仔中心・外觀'}],
            'curated:spca-tsing-yi':[{'url':'https://www.spca.org.hk/wp-content/uploads/2023/12/spca_tsingyi.jpg','source_url':'https://www.spca.org.hk/about-us/spca-centres/','credit':'香港愛護動物協會 SPCA','alt':'愛護動物協會青衣中心・外觀'}],
            'curated:airside':[{'url':'https://m1.airside.com.hk/assets/collapsible-item-with-icons/HeadBanner_2100x1400-03-min.jpg','source_url':'https://www.airside.com.hk/zh-hk/visit/pet-friendly-paradise','credit':'AIRSIDE','alt':'AIRSIDE・寵物共融區'}],
        }
        for pid,photos in official.items():
            valid=[]
            for photo in photos:
                try:
                    async with container.client.stream('GET',photo['url']) as response:
                        response.raise_for_status()
                        if response.headers.get('content-type','').startswith('image/'):
                            valid.append(photo)
                except Exception:
                    logging.warning('Official photo unavailable: %s',pid)
            if valid:output[pid]=valid
        payload={'checked_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(),'places':output,'pages':statuses}
        temporary=MANIFEST.with_suffix('.tmp');temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2));temporary.replace(MANIFEST)
        attach_photos(snapshot.places)
        await container.cache.set_json('snapshot:v1',snapshot.model_dump(mode='json'),ttl=86400*7)
        temporary=container.pets.snapshot_path.with_suffix('.tmp');temporary.write_text(snapshot.model_dump_json(indent=2));temporary.replace(container.pets.snapshot_path)
        print(json.dumps({'places_with_photos':sum(bool(p.photos) for p in snapshot.places),'photos':sum(len(p.photos) for p in snapshot.places),'failed_pages':sum(s['status']!='ready' for s in statuses.values())},ensure_ascii=False))
    finally:
        await container.aclose()

if __name__=='__main__':
    asyncio.run(main())
