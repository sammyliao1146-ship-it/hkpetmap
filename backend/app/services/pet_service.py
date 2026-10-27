import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from backend.app.cache.redis_cache import RedisCache
from backend.app.data import adapters
from backend.app.data.activity_sources import SOURCES as ACTIVITY_SOURCES, fetch_source
from backend.app.data.malls import load_malls, merge_malls, mall_source_status, MALL_SOURCE
from backend.app.data.photos import attach_photos
from backend.app.data.google_cuisines import attach_google_cuisines
from backend.app.data.restaurant_details import attach_restaurant_details
from backend.app.data.localization import enrich_english, CATEGORY_EN, CUISINE_EN
from backend.app.data.sources import (AFCD_COURSES, CATEGORIES, CUISINES, FEHD_DATA, FEHD_URL,
    HOTEL_DATA, HOTEL_URL, LAYERS, RESTAURANT_LAYER, SPCA_URL, VET_URL)
from backend.app.models.pet import Activity, Place, Snapshot

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
DATA = Path(__file__).resolve().parents[1] / 'data'
HK = ZoneInfo('Asia/Hong_Kong')


class PetService:
    def __init__(self, cache: RedisCache, client: httpx.AsyncClient, snapshot_path: Path | None = None, *, max_age_seconds: float = 21600):
        self.cache, self.client = cache, client
        self.snapshot_path = snapshot_path or ROOT / 'data' / 'pet-snapshot.json'
        self.snapshot: Snapshot | None = None
        self.max_age_seconds=max_age_seconds
        self._load_lock=asyncio.Lock()
        self._loaded_signature=None
        self._lock = asyncio.Lock()
        self._next_retry = datetime.min.replace(tzinfo=HK)

    async def _snapshot_signature(self):
        revision=await self.cache.get_bytes('snapshot:revision')
        try:
            stat=self.snapshot_path.stat();disk=(stat.st_mtime_ns,stat.st_size)
        except OSError:disk=None
        return revision,disk

    async def load(self):
        async with self._load_lock:
            # Observe revision BEFORE reading payload to avoid acknowledging a newer
            # publication after loading an older payload.
            signature=await self._snapshot_signature()
            candidates=[]
            raw=await self.cache.get_json('snapshot:v1')
            if raw:
                try:candidates.append(Snapshot.model_validate(raw))
                except (ValueError,TypeError):log.warning('Invalid cached pet snapshot')
            if self.snapshot_path.exists():
                try:candidates.append(Snapshot.model_validate_json(self.snapshot_path.read_text()))
                except (ValueError,OSError):log.warning('Invalid local pet snapshot')
            if candidates:
                # Activities-only updates keep fetched_at, but always advance published_at.
                snapshot=max(candidates,key=lambda x:x.published_at or x.fetched_at)
                malls=load_malls()
                snapshot.places=merge_malls(snapshot.places,malls)
                snapshot.sources=[row for row in snapshot.sources if row['key']!='malls']
                snapshot.sources.append(mall_source_status(malls))
                attach_google_cuisines(snapshot.places)
                attach_restaurant_details(snapshot.places)
                attach_photos(snapshot.places)
                enrich_english(snapshot.places,snapshot.activities)
                self.snapshot=snapshot # Swap only after complete enrichment.
            self._loaded_signature=signature

    async def reload_if_changed(self):
        if await self._snapshot_signature()!=self._loaded_signature:
            await self.load()

    async def ensure(self):
        """Read-only compatibility for callers. Never fetch upstream on a request."""
        await self.reload_if_changed()

    def refresh_due(self):
        now=datetime.now(HK)
        return (not self.snapshot or now-self.snapshot.fetched_at>timedelta(seconds=self.max_age_seconds)) and now>=self._next_retry

    async def _get(self, url, **kwargs):
        r = await self.client.get(url, **kwargs)
        r.raise_for_status()
        return r

    async def _restaurants(self):
        rows = (await self._get(FEHD_DATA)).json()
        if not isinstance(rows, list) or not rows:
            raise ValueError('Empty FEHD response')
        ids = [str(row.get('licence', '')) for row in rows]
        features = []
        # Read only approved dog-friendly premises' coordinates, not all HK restaurants.
        for offset in range(0, len(ids), 100):
            values = ','.join("'"+v+"'" for v in ids[offset:offset+100] if re.fullmatch(r'\d{10}', v))
            if values:
                features.extend(await adapters.arcgis(self.client, RESTAURANT_LAYER, f'SEARCH02_TC IN ({values})'))
        result = adapters.normalize_restaurants(rows, features)
        enrichment = json.loads((DATA/'cuisine_enrichment.json').read_text())
        for p in result:
            meta = enrichment['by_licence'].get(p.licence_number)
            if not meta:
                meta = next((m for m in enrichment['by_brand'] if re.fullmatch(m['pattern'], p.name_en or p.name, re.I)), None)
            if meta:
                # Validate curated source + labels, never guess cuisine from a venue name.
                p = Place.model_validate({**p.model_dump(), 'cuisines': meta['cuisines'], 'cuisine_source': meta['source_url']})
            yield p

    async def _layer(self, layer):
        records = await adapters.arcgis(self.client, layer)
        items, skipped = [], 0
        for feature in records:
            try:
                items.append(adapters.normalize_layer(layer, feature))
            except (ValueError, KeyError, TypeError, IndexError):
                skipped += 1
        if not items:
            raise ValueError('未能讀取任何有效場地記錄')
        return items, skipped

    async def _hotels(self):
        return adapters.normalize_hotels((await self._get(HOTEL_DATA)).text), 0

    async def _vets(self):
        html = (await self._get(VET_URL)).text
        soup = BeautifulSoup(html, 'html.parser')
        links = [a for a in soup.select('a[href]') if 'Vet_Clinics_List_' in a['href'] and a.get_text(strip=True)]
        if not links:
            raise ValueError('官方診所 PDF 連結未有提供')
        url = urljoin(VET_URL, links[0]['href'])
        if urlparse(url).hostname != 'www.pets.gov.hk':
            raise ValueError('Unexpected vet list host')
        items = await asyncio.to_thread(adapters.parse_vets, (await self._get(url)).content, url)
        return items, 0

    async def _curated(self):
        return [Place.model_validate(v) for v in json.loads((DATA/'curated_places.json').read_text()) if v['category'] != 'malls'], 0

    async def _malls(self):
        return load_malls(), 0

    async def _geocode(self, items):
        # Keep unknown/unmatched addresses off the map; never substitute district centres.
        semaphore = asyncio.Semaphore(3)
        old = {p.id: p for p in self.snapshot.places} if self.snapshot else {}
        async def locate(place):
            if place.latitude is not None or not (place.address_en or place.address):
                return
            previous = old.get(place.id)
            if previous and previous.address == place.address and previous.latitude is not None:
                place.latitude, place.longitude, place.coordinate_source = previous.latitude, previous.longitude, previous.coordinate_source
                return
            address = place.address_en or place.address
            key = 'als:'+adapters.identity(address)
            hit = await self.cache.get_json(key)
            if hit is None:
                async with semaphore:
                    try:
                        response = await self._get('https://www.als.gov.hk/lookup', params={'q': address, 'n': 1}, headers={'Accept':'application/json'})
                        options = response.json().get('SuggestedAddress', [])
                        hit = {'matched': False}
                        if options and float(options[0].get('ValidationInformation', {}).get('Score', 0)) >= 80:
                            g = options[0]['Address']['PremisesAddress']['GeospatialInformation']
                            hit = {'matched':True,'lat':float(g['Latitude']),'lon':float(g['Longitude'])}
                        await self.cache.set_json(key, hit, ttl=86400*30)
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        return
                    finally:
                        await asyncio.sleep(.2)
            if hit.get('matched') and 22.1 <= hit['lat'] <= 22.6 and 113.8 <= hit['lon'] <= 114.5:
                place.latitude, place.longitude = hit['lat'], hit['lon']
                place.coordinate_source = '政府地址查找服務 ALS；地址配對代表點，唔一定係入口'
        await asyncio.gather(*(locate(p) for p in items))

    async def refresh(self, *, force=False, geocode=False, activities_only=False, before_publish=None, require_shared=False):
        async with self._lock:
            now = datetime.now(HK)
            if not force and now < self._next_retry:
                return
            self._next_retry = now + timedelta(minutes=10)
            old = self.snapshot
            places, activities, statuses = [], [], []
            if activities_only and old:
                places = list(old.places)
                statuses = [s for s in old.sources if s['key'] != 'activities' and s['key'] not in ACTIVITY_SOURCES]
            async def restaurants():
                return [p async for p in self._restaurants()], 0
            async def courses():
                response = await self._get(SPCA_URL)
                return adapters.parse_courses(response.text, now.date()), 0
            jobs = [('restaurants', FEHD_URL, restaurants), ('hotels', HOTEL_URL, self._hotels),
                    ('vets', VET_URL, self._vets), ('curated', 'https://www.airside.com.hk/zh-hk/visit/pet-friendly-paradise', self._curated),
                    ('malls', MALL_SOURCE, self._malls), ('activities', SPCA_URL, courses)]
            jobs += [(l.key, l.url, lambda l=l: self._layer(l)) for l in LAYERS]
            if activities_only:
                jobs = [j for j in jobs if j[0] == 'activities']
            jobs += [(key, meta['url'], lambda key=key: fetch_source(self._get, key, now.date()))
                     for key, meta in ACTIVITY_SOURCES.items()]
            async def run(key, url, fetch):
                try:
                    items, skipped = await fetch()
                    return key, url, items, skipped, None
                except Exception as exc:
                    log.warning('Pet source %s failed: %s', key, type(exc).__name__)
                    return key, url, [], 0, type(exc).__name__
            results = await asyncio.gather(*(run(*j) for j in jobs))
            for key, url, items, skipped, error in results:
                if error and old:
                    if key == 'activities':
                        prefixes = tuple(m['prefix'] for m in ACTIVITY_SOURCES.values())
                        items = [a for a in old.activities if not a.id.startswith(prefixes)]
                    elif key in ACTIVITY_SOURCES:
                        items = [a for a in old.activities if a.id.startswith(ACTIVITY_SOURCES[key]['prefix'])]
                    elif key == 'curated':
                        items = [p for p in old.places if p.id.startswith('curated:') and p.category != 'malls']
                    elif key == 'malls':
                        items = [p for p in old.places if p.category == 'malls']
                    else:
                        items = [p for p in old.places if p.category == key and not p.id.startswith('curated:')]
                previous_status = next((s for s in old.sources if s['key']==key), {}) if old else {}
                statuses.append({'key':key, 'label':ACTIVITY_SOURCES[key]['name'] if key in ACTIVITY_SOURCES else CATEGORIES.get(key, '寵物課程' if key=='activities' else '官方場地補充'),
                    'url':url, 'status':'stale' if error and items else 'error' if error else 'ready',
                    'count':len(items), 'skipped':skipped,
                    'fetched_at':previous_status.get('fetched_at') if error else now.isoformat(),
                    'message': '更新唔到，顯示舊快照。' if error and items else '暫時讀唔到呢個來源。' if error else ''})
                if key == 'activities' or key in ACTIVITY_SOURCES:
                    activities.extend(items)
                else:
                    places.extend(items)
            # Preserve previously resolved coordinates even on routine refreshes.
            if old:
                previous = {p.id:p for p in old.places}
                for p in places:
                    prior = previous.get(p.id)
                    if p.latitude is None and prior and prior.address == p.address:
                        p.latitude, p.longitude, p.coordinate_source = prior.latitude, prior.longitude, prior.coordinate_source
            if geocode:
                await self._geocode(places)
            attach_google_cuisines(places)
            attach_restaurant_details(places)
            attach_photos(places)
            enrich_english(places,activities)
            activities = [a for a in activities if a.registration_status != 'cancelled'
                          and (not a.end_date or a.end_date >= now.date().isoformat())]
            activities.sort(key=lambda a: (a.start_date or '9999', a.name, a.id))
            next_snapshot = Snapshot(published_at=now,fetched_at=old.fetched_at if activities_only and old else now,
                                     places=places, activities=activities, sources=statuses)
            if before_publish:await before_publish()
            await self.cache.publish_snapshot(next_snapshot.model_dump(mode='json'),now.isoformat(),ttl=86400*7,require_shared=require_shared)
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.snapshot_path.with_suffix('.tmp')
            temporary.write_text(next_snapshot.model_dump_json(indent=2))
            temporary.replace(self.snapshot_path)
            self.snapshot=next_snapshot

    def _status(self):
        if not self.snapshot:
            return 'not_synced'
        if datetime.now(HK) - self.snapshot.fetched_at > timedelta(seconds=self.max_age_seconds):
            return 'stale'
        return 'partial' if any(s['status'] != 'ready' for s in self.snapshot.sources) else 'ready'

    def catalogue(self):
        return {'status': self._status(), 'fetched_at':self.snapshot.fetched_at.isoformat() if self.snapshot else None,
            'categories':[{'key':k,'label':v,'label_en':CATEGORY_EN[k]} for k,v in CATEGORIES.items()], 'cuisines':CUISINES, 'cuisine_labels':[{'value':v,'label':v,'label_en':CUISINE_EN[v]} for v in CUISINES],
            'sources':self.snapshot.sources if self.snapshot else [],
            'transport_services':json.loads((DATA/'transport_services.json').read_text()),
            'activity_sources':[{'name':'SPCA 狗隻訓練課程','name_en':'SPCA dog training courses','url':SPCA_URL,'integration':'public_web_table'},
                                *[{k:v for k,v in meta.items() if k != 'prefix'} for meta in ACTIVITY_SOURCES.values()],
                                {'name':'漁護署狗隻訓練課程','name_en':'AFCD dog training courses','url':AFCD_COURSES,'integration':'official_link_only'}],
            'message':'政府同機構公開資料，唔係全港完整名單。名額、價格同攜寵條件未有提供就係未知。'}

    def places(self, *, mode='', categories=(), cuisines=(), district='', query=''):
        items = self.snapshot.places if self.snapshot else []
        if mode:
            items = [p for p in items if (p.category=='restaurants') == (mode=='restaurants')]
        if categories:
            items = [p for p in items if p.category in categories]
        if cuisines:
            items = [p for p in items if set(p.cuisines or ['未分類']) & set(cuisines)]
        if district:
            items = [p for p in items if district.removesuffix('區') in (p.district or '')]
        if query:
            items = [p for p in items if query.casefold() in ' '.join(filter(None,[p.name,p.name_en,p.address,p.address_en,p.restaurant_details.display_name if p.restaurant_details else None])).casefold()]
        return {'status':self._status(), 'fetched_at':self.snapshot.fetched_at.isoformat() if self.snapshot else None,
            'items':[p.model_dump(mode='json') for p in items], 'total':len(items),
            'mapped':sum(p.latitude is not None for p in items), 'sources':self.snapshot.sources if self.snapshot else []}

    def activities(self, *, category='', query='', on_date='', district=''):
        if on_date:
            datetime.strptime(on_date, '%Y-%m-%d')
        items = self.snapshot.activities if self.snapshot else []
        items = [a for a in items if (not category or a.category==category)
            and (not district or district.removesuffix('區') in (a.district or ''))
            and (not query or query.casefold() in f'{a.name} {a.name_en} {a.description}'.casefold())
            and (not on_date or (a.start_date is not None and a.start_date <= on_date and (a.end_date or a.start_date) >= on_date))]
        return {'status':self._status(), 'fetched_at':self.snapshot.fetched_at.isoformat() if self.snapshot else None,
            'items':[a.model_dump(mode='json') for a in items], 'total':len(items),
            'message':'日期欄保留主辦方原文；未公佈嘅單堂日期唔會推算。報名狀態同剩餘名額分開顯示；未知名額保持空值。'}
