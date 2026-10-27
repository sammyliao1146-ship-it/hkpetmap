"""Government car-park data with shared caching and last-known-data fallback."""
import asyncio
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

PARKING_URL = 'https://api.data.gov.hk/v1/carpark-info-vacancy'
SOURCE_URL = 'https://data.gov.hk/en-data/dataset/hk-dpo-datagovhk1-carpark-info-vacancy'
HK = ZoneInfo('Asia/Hong_Kong')


def distance_m(a, b, c, d):
    lat1, lat2 = math.radians(a), math.radians(c)
    delta_lat, delta_lon = lat2-lat1, math.radians(d-b)
    value = math.sin(delta_lat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(delta_lon/2)**2
    return 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0, 1-value)))


class ParkingService:
    def __init__(self, cache, client: httpx.AsyncClient, snapshot_path=None):
        self.cache, self.client = cache, client
        self.snapshot_path = Path(snapshot_path) if snapshot_path else Path(__file__).resolve().parents[3]/'data/parking-snapshot.json'
        self._lock = asyncio.Lock()
        self._data = None
        self._retry_after = {}
        self._failed = set()

    async def _fetch(self, kind, language):
        response = await self.client.get(PARKING_URL, params={
            'data':kind, 'vehicleTypes':'privateCar', 'lang':language}, timeout=8)
        response.raise_for_status()
        rows = response.json().get('results')
        if not isinstance(rows, list) or not rows:
            raise ValueError('Empty or invalid government parking response')
        return rows

    async def _load(self):
        async with self._lock:
            if self._data is None:
                self._data = await self.cache.get_json('parking:v1')
                if not isinstance(self._data, dict):
                    try:
                        self._data = json.loads(self.snapshot_path.read_text())
                    except (OSError, ValueError):
                        self._data = {}
            data = dict(self._data)
            now = datetime.now(timezone.utc).timestamp()
            jobs = []
            keys = []
            for key, kind, language, ttl in (
                ('info_en','info','en_US',86400), ('info_zh','info','zh_TW',86400),
                ('vacancy','vacancy','en_US',60),
            ):
                if (not data.get(key) or now-data.get(key+'_at',0) > ttl) and now >= self._retry_after.get(key,0):
                    keys.append(key); jobs.append(self._fetch(kind, language))
            for key, result in zip(keys, await asyncio.gather(*jobs, return_exceptions=True)):
                if isinstance(result, Exception):
                    self._failed.add(key)
                    self._retry_after[key] = now+30
                else:
                    data[key], data[key+'_at'] = result, now
                    self._failed.discard(key)
            if keys:
                self._data = data
                await self.cache.set_json('parking:v1', data, 7*86400)
                try:
                    self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.snapshot_path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(data, ensure_ascii=False))
                    temporary.replace(self.snapshot_path)
                except OSError:
                    pass
            return data, sorted(self._failed)

    @staticmethod
    def _vacancy(row, now):
        values = row.get('privateCar') or []
        if not isinstance(values, list) or not values:
            return None, None, 'unknown'
        value = values[0]
        timestamp = value.get('lastupdate')
        try:
            updated = datetime.fromisoformat(timestamp)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=HK)
            fresh = -300 <= (now-updated).total_seconds() <= 900
        except (TypeError, ValueError):
            fresh = False
        count = value.get('vacancy')
        if not isinstance(count, (int,float)) or isinstance(count,bool) or count < 0:
            count = None
        status = 'stale' if not fresh else ('full' if value.get('vacancy_type') == 'F' or count == 0 else 'available' if count is not None else 'unknown')
        return count, timestamp, status

    async def list(self, language='en'):
        data, errors = await self._load()
        en = {str(r.get('park_Id')):r for r in data.get('info_en',[]) if isinstance(r,dict)}
        zh = {str(r.get('park_Id')):r for r in data.get('info_zh',[]) if isinstance(r,dict)}
        vacancies = {str(r.get('park_Id')):r for r in data.get('vacancy',[]) if isinstance(r,dict)}
        now = datetime.now(timezone.utc)
        items = []
        for key in sorted(en.keys() | zh.keys()):
            english, chinese = en.get(key,{}), zh.get(key,{})
            primary = english if language=='en' else chinese
            primary = primary or english or chinese
            try:
                lat, lon = float(primary['latitude']), float(primary['longitude'])
                if not math.isfinite(lat) or not math.isfinite(lon) or not 22 <= lat <= 23 or not 113 <= lon <= 115:
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            vacancy, updated, status = self._vacancy(vacancies.get(key,{}), now)
            vehicle = primary.get('privateCar') or {}
            hourly = vehicle.get('hourlyCharges') or []
            height_limits = primary.get('heightLimits') or []
            prices = [r['price'] for r in hourly if isinstance(r,dict) and isinstance(r.get('price'),(int,float))]
            fee = (f"HK${min(prices):g}/hour" if min(prices)==max(prices) else f"HK${min(prices):g}–{max(prices):g}/hour") if prices else None
            notes_en = ['Parking access does not confirm pet access to the venue. Check the latest operator rules.']
            notes_zh = ['停車場資訊唔代表已確認場地攜寵准入，請核實場地最新規則。']
            items.append({
                'id':'parking:'+key, 'source_id':key, 'category':'parking',
                'name':primary.get('name') or english.get('name') or key,
                'name_en':english.get('name'), 'name_zh':chinese.get('name'),
                'address':primary.get('displayAddress'), 'address_en':english.get('displayAddress'),
                'latitude':lat, 'longitude':lon, 'district':primary.get('district'),
                'coordinate_source':'Hong Kong Government Parking Vacancy Data',
                'source_url':SOURCE_URL, 'source_name':'Government parking data', 'source_name_en':'Government parking data',
                'pet_policy':'unknown', 'notes':notes_en if language=='en' else notes_zh, 'notes_en':notes_en,
                'photos':[], 'cuisines':[], 'cuisine_source':None, 'licence_number':None, 'rules_url':None,
                'telephone':primary.get('contactNo'), 'website':primary.get('website'),
                'opening_hours':None, 'opening_hours_en':None, 'opening_hours_details':primary.get('openingHours') or [],
                'hourly_charges':hourly, 'fee_summary':fee, 'height_limits':height_limits,
                'vacancy':vacancy, 'vacancy_updated_at':updated, 'vacancy_status':status,
                'stale':status=='stale', 'last_updated':updated, 'remaining':vacancy,
                'source_updated_at':updated,
                'navigation_url':f'https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=driving',
            })
        fetched = max((data.get(k+'_at',0) for k in ('info_en','info_zh','vacancy')), default=0)
        return {'status':'partial' if errors and items else 'ready' if items else 'unavailable',
                'fetched_at':datetime.fromtimestamp(fetched, timezone.utc).isoformat() if fetched else None,
                'items':items, 'total':len(items), 'source_url':SOURCE_URL,
                'message':'Some upstream data is unavailable; last known records are shown.' if errors and items else 'Government participating car parks; coverage is not exhaustive.'}

    async def nearby(self, latitude, longitude, radius_m=1000, limit=10, language='en'):
        if not (math.isfinite(latitude) and math.isfinite(longitude) and -90<=latitude<=90 and -180<=longitude<=180):
            raise ValueError('Invalid origin coordinates')
        if not 0 < radius_m <= 50000 or not 1 <= limit <= 1000:
            raise ValueError('Invalid parking radius or limit')
        data = await self.list(language)
        rows = [{**r,'distance_m':distance_m(latitude,longitude,r['latitude'],r['longitude'])} for r in data['items']]
        rows = sorted((r for r in rows if r['distance_m'] <= radius_m), key=lambda r:r['distance_m'])
        return {**data,'items':[{**r,'distance_m':round(r['distance_m'])} for r in rows[:limit]],'total':len(rows), 'radius_m':radius_m,
                'distance_type':'straight_line'}
