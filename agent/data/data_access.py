"""Bounded, read-only pet queries shared by function tools and MCP."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
from urllib.parse import urlencode
from backend.app.data.sources import CATEGORIES, CUISINES
from agent.data.place_search import select_places, valid_origin

TRANSPORT_RULES = json.loads((Path(__file__).resolve().parents[2] / 'backend/app/data/transport_rules.json').read_text())

MODE_ALIASES = {'restaurant': 'restaurants', 'dining': 'restaurants', 'food': 'restaurants', '餐廳': 'restaurants',
                'facility': 'facilities', 'place': 'facilities', 'places': 'facilities', '設施': 'facilities'}
CUISINE_ALIASES = {'japanese': '日式', 'korean': '韓式', 'chinese': '中式', 'cantonese': '港式', 'hong kong': '港式',
                   'western': '西式', 'italian': '意式／薄餅', 'pizza': '意式／薄餅', 'thai': '泰式', 'vietnamese': '越式',
                   'dessert': '甜品', 'vegetarian': '素食', 'vegan': '素食', 'cafe': '咖啡／輕食', 'coffee': '咖啡／輕食',
                   '咖啡': '咖啡／輕食', '輕食': '咖啡／輕食', '意式': '意式／薄餅', '薄餅': '意式／薄餅'}

def _norm(value, valid, aliases):
    """Map common model-supplied spellings onto catalogue values; unknown values are returned untouched."""
    if not value or value in valid:
        return value
    key = value.strip().lower()
    return aliases.get(key) or next((v for v in valid if v.lower() == key), value)

class PetDataAccess:
    def __init__(self, pets, origin=None):
        self.pets = pets
        self.origin=valid_origin(*origin) if origin is not None else None
        self.seen_places={}
        self.direction_sources=[]

    async def catalog(self):
        return {
            'current_time_hk':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(), **self.pets.catalogue()}

    async def search_places(self, mode='', category='', cuisine='', district='', query='', limit=8, *, sort_by='default', latitude=None, longitude=None, origin_place_id='', radius_m=None, min_rating=None, max_price=None):
        if not 1 <= limit <= 20:
            raise ValueError('limit must be 1–20')
        mode = _norm(mode, {'restaurants', 'facilities'}, MODE_ALIASES)
        category = _norm(category, CATEGORIES, MODE_ALIASES)
        cuisine = _norm(cuisine, CUISINES, CUISINE_ALIASES)
        if mode not in {'', 'restaurants', 'facilities'} or (category and category not in CATEGORIES) or (cuisine and cuisine not in CUISINES):
            # Recoverable by the agent in one retry, unlike a raised tool error.
            return {'query_status': 'invalid_filter', 'items': [], 'total': 0, 'returned': 0,
                    'message': 'Unsupported mode/category/cuisine. Retry with exactly these values, or drop the filter.',
                    'valid_modes': ['restaurants', 'facilities'], 'valid_categories': list(CATEGORIES), 'valid_cuisines': CUISINES}
        data = self.pets.places(mode=mode, categories=[category] if category else [], cuisines=[cuisine] if cuisine else [], district=district, query=query)
        if origin_place_id and (latitude is not None or longitude is not None):
            raise ValueError('Use coordinates or origin_place_id, not both')
        origin=self.origin
        if latitude is not None or longitude is not None:origin=valid_origin(latitude,longitude)
        if origin_place_id:
            source=next((p for p in self.pets.places()['items'] if p['id']==origin_place_id),None)
            origin=(source['latitude'],source['longitude']) if source and source.get('latitude') is not None and source.get('longitude') is not None else None
        result = select_places(data,sort_by=sort_by,origin=origin,radius_m=radius_m,min_rating=min_rating,limit=limit,max_price=max_price)
        self._remember(result['items'])
        return result

    def _remember(self, items):
        for p in items:
            self.seen_places[p['id']] = p

    def mentioned_places(self, answer: str, limit: int = 5):
        """Places returned by tools in this request whose name appears in the answer, in answer order."""
        text = answer.lower()
        found = []
        for p in self.seen_places.values():
            names = [n for n in (p.get('name'), p.get('name_en'), (p.get('restaurant_details') or {}).get('display_name')) if n and len(n.strip()) >= 2]
            positions = [text.find(n.strip().lower()) for n in names]
            positions = [i for i in positions if i >= 0]
            if positions:
                found.append((min(positions), p['id'], p.get('name') or p.get('name_en') or p['id']))
        return [{'id': i, 'name': n} for _, i, n in sorted(found)[:limit]]

    async def place_details(self, place_id):
        data = self.pets.places()
        item = next((p for p in data['items'] if p['id']==place_id),None)
        if item: self._remember([item])
        return {'status':data['status'], 'fetched_at':data['fetched_at'], 'found':item is not None, 'place':item,
                'sources':data['sources'], 'remaining':None}

    async def search_activities(self, query='', category='', district='', limit=8):
        if not 1 <= limit <= 20:
            raise ValueError('limit must be 1–20')
        data = self.pets.activities(query=query, category=category, district=district)
        data['items'] = data['items'][:limit]
        return data

    async def activity_details(self, activity_id):
        data = self.pets.activities()
        item = next((a for a in data['items'] if a['id']==activity_id),None)
        return {'status':data['status'], 'fetched_at':data['fetched_at'], 'found':item is not None, 'activity':item}

    async def transport(self):
        return {'status':self.pets.catalogue()['status'], 'services':self.pets.catalogue()['transport_services'],
                'restrictions':TRANSPORT_RULES,
                'places':(await self.search_places(category='transport')),
                'message':'交通守則資料，唔係即時路線、車價、班次或訂位服務。'}

    async def directions(self, place_id):
        detail = await self.place_details(place_id)
        place = detail['place']
        if not place:
            return {'status':'needs_destination','message':'Ask which restaurant or map venue the user means.'}
        latitude, longitude = place.get('latitude'), place.get('longitude')
        address = place.get('address') or place.get('address_en')
        if latitude is not None and longitude is not None:
            destination = f'{latitude},{longitude}'
        elif address:
            destination = f"{place['name']} {address}"
        else:
            return {'status':'missing_destination_details','place_id':place_id,
                    'message':'No saved address or coordinates. Ask the user to confirm the destination.'}
        links = []
        for mode in ('walking','driving'):
            params = {'api':'1','destination':destination,'travelmode':mode}
            if self.origin:
                params['origin'] = f'{self.origin[0]},{self.origin[1]}'
            url = 'https://www.google.com/maps/dir/?' + urlencode(params)
            links.append({'mode':mode,'url':url})
            self.direction_sources.append({'title':f"{place['name']} — {mode} directions",'url':url})
        self.direction_sources.extend({'title':r['mode']+' pet restrictions','url':r['source_url']} for r in TRANSPORT_RULES)
        return {'status':'ready','place':place,'directions':links,'restrictions':TRANSPORT_RULES,
                'services':self.pets.catalogue()['transport_services'],
                'message':'External navigation links only, not verified routes or pet access. No transit route is endorsed. Travel times and fares are unknown.'}
