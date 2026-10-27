"""Validated outing plans grouped around real parking locations, never fabricated routes."""
import asyncio
from math import asin, cos, radians, sin, sqrt
import secrets
from uuid import uuid4

from agent.subagents.trip_planner import select_plan_stops
from backend.app.models.plan import PlanRequest

REGIONS = {
    'hong_kong_island': {'中西', '東', '南', '灣仔'},
    'kowloon': {'九龍城', '觀塘', '深水埗', '黃大仙', '油尖旺'},
    'new_territories': {'離島', '葵青', '北', '西貢', '沙田', '大埔', '荃灣', '屯門', '元朗'},
}
DESTINATIONS = [
    {'id':'west-kowloon','name':'西九文化區','name_en':'West Kowloon','region':'kowloon','anchor_ids':['parks:118'],'source_url':'https://www.westk.hk/'},
    {'id':'science-park','name':'香港科學園','name_en':'Hong Kong Science Park','region':'new_territories','anchor_ids':[], 'anchor_query':'Science Park','source_url':'https://www.hkstp.org/en/park-life/pet-friendly-environment'},
    {'id':'stanley','name':'赤柱','name_en':'Stanley','region':'hong_kong_island','anchor_ids':['curated:mall:stanley-plaza-stanley-plaza','inclusive_parks:157'],'source_url':'https://www.stanleyplaza.com/'},
    {'id':'kwun-tong-waterfront','name':'觀塘海濱','name_en':'Kwun Tong Waterfront','region':'kowloon','anchor_ids':['inclusive_parks:23']},
    {'id':'central-waterfront','name':'中環海濱','name_en':'Central Waterfront','region':'hong_kong_island','anchor_ids':['pet_parks:18','inclusive_parks:120']},
    {'id':'tseung-kwan-o','name':'將軍澳南及環保大道','name_en':'Tseung Kwan O South / Wan Po Road','region':'new_territories','anchor_ids':['pet_parks:7','pet_parks:46']},
    {'id':'tai-po-waterfront','name':'大埔海濱','name_en':'Tai Po Waterfront','region':'new_territories','anchor_ids':['inclusive_parks:106']},
    {'id':'tung-chung','name':'東涌北及小炮台','name_en':'Tung Chung North / Battery Park','region':'new_territories','anchor_ids':['pet_parks:5','pet_parks:1']},
    {'id':'lam-tei','name':'藍地寵物公園','name_en':'Lam Tei Pet Garden','region':'new_territories','anchor_ids':['pet_parks:52']},
]
CATEGORIES = {'park': {'parks','pet_parks','inclusive_parks'}, 'vet': {'vets'}, 'mall': {'malls'}}
CUISINE_ALIASES = {'sushi':'日式','壽司':'日式','寿司':'日式','japanese':'日式','日式':'日式',
                   'cafe':'咖啡／輕食','coffee':'咖啡／輕食','italian':'意式／薄餅','pizza':'意式／薄餅',
                   'western':'西式','thai':'泰式','chinese':'中式','korean':'韓式','any':'','不限':''}


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(radians, (a['latitude'], a['longitude'], b['latitude'], b['longitude']))
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 6371000 * 2 * asin(min(1, sqrt(h)))


def has_location(p):
    return isinstance(p.get('latitude'), (int,float)) and isinstance(p.get('longitude'), (int,float))


def region_matches(p, region):
    if region == 'any': return True
    district = (p.get('district') or '').removesuffix('區')
    return district in REGIONS.get(region, set())


def destinations(places, region='any'):
    by_id = {p['id']:p for p in places if has_location(p)}
    result=[]
    for item in DESTINATIONS:
        if region != 'any' and item['region'] != region: continue
        anchors=[by_id[i] for i in item['anchor_ids'] if i in by_id]
        if not anchors and item.get('anchor_query'):
            query=item['anchor_query'].lower()
            # Use an existing government-located venue as a search anchor, never claim it is a park entrance.
            anchors=[p for p in places if has_location(p) and query in ' '.join(str(p.get(k) or '') for k in ('address','address_en')).lower()]
        if anchors:
            result.append({**item,'latitude':anchors[0]['latitude'],'longitude':anchors[0]['longitude'],
                           'anchor_place_ids':[p['id'] for p in anchors],
                           'source_url':item.get('source_url') or anchors[0]['source_url']})
    return result


def options(places):
    return {'regions':[{'id':'any','name':'全港','name_en':'All Hong Kong'},
                       {'id':'hong_kong_island','name':'港島','name_en':'Hong Kong Island'},
                       {'id':'kowloon','name':'九龍','name_en':'Kowloon'},
                       {'id':'new_territories','name':'新界及離島','name_en':'New Territories & Islands'}],
            'destinations':destinations(places), 'radius_m':1000}


def local_areas(places, activities, request):
    """Ordinary planning may use any eligible local venue as its area anchor."""
    categories=set().union(*(CATEGORIES.get(i,set()) for i in request.interests))
    activity_places={a.get('place_id') for a in activities} if 'activity' in request.interests else set()
    eligible=[p for p in places if has_location(p) and region_matches(p,request.region)
              and (p['category'] in categories or p['id'] in activity_places)]
    eligible=[p for p in eligible if p['category']!='parks' or p.get('pet_policy')!='unknown']
    if request.origin:
        origin={'latitude':request.origin.latitude,'longitude':request.origin.longitude}
        eligible.sort(key=lambda p:distance(p,origin))
    # Round-robin districts AND modules prevents the first imported region/category from dominating.
    buckets={}
    for p in eligible:
        for interest in request.interests:
            if p['category'] in CATEGORIES.get(interest,set()) or interest=='activity' and p['id'] in activity_places:
                buckets.setdefault((p.get('district') or '',interest),[]).append(p)
    ordered=[];seen=set()
    for index in range(max((len(b) for b in buckets.values()),default=0)):
        for bucket in buckets.values():
            if index<len(bucket) and bucket[index]['id'] not in seen:
                ordered.append(bucket[index]);seen.add(bucket[index]['id'])
    result=[]
    for p in ordered[:80]:
        region=next((r for r in REGIONS if region_matches(p,r)),request.region)
        result.append({'id':'area:'+p['id'],'name':p['name'],'name_en':p.get('name_en') or p['name'],
                       'region':region,'latitude':p['latitude'],'longitude':p['longitude'],
                       'anchor_place_ids':[p['id']],'source_url':p['source_url']})
    return result


def build_candidates(places, activities, parking, request, destination):
    # Once an area is selected, an 'any region' request must not mix opposite harbour shores.
    effective_region=destination.get('region',request.region) if request.region=='any' else request.region
    local=[p for p in places if has_location(p) and region_matches(p,effective_region)
           and distance(p,destination) <= 4500]
    parking=[p for p in parking if has_location(p) and distance(p,destination) <= 5500]
    cuisine=CUISINE_ALIASES.get(request.cuisine.strip().lower(), request.cuisine.strip())
    candidates=[]

    def add(p, purpose, activity=None):
        eligible=[c['id'] for c in parking if distance(p,c) <= 1000]
        if not eligible:return
        item={'id':('activity:'+activity['id']) if activity else p['id'], 'place':p,
              'purpose':purpose,'parking_ids':eligible,'anchor_distance_m':round(distance(p,destination))}
        if activity:item['activity']=activity
        candidates.append(item)

    for purpose in dict.fromkeys(request.interests):
        if purpose == 'activity':
            by_id={p['id']:p for p in local}
            for a in activities:
                if a.get('registration_status') == 'cancelled':continue
                # Exclude clearly expired/upcoming activities; unknown dates remain visibly unconfirmed.
                if a.get('start_date') and a['start_date'] > request.date.isoformat():continue
                if a.get('end_date') and a['end_date'] < request.date.isoformat():continue
                if a.get('place_id') in by_id:add(by_id[a['place_id']],purpose,a)
        else:
            pool=[p for p in local if p['category'] in CATEGORIES[purpose]]
            if purpose=='park':
                pool=[p for p in pool if p.get('pet_policy') != 'unknown' or p['id'] in destination['anchor_place_ids']]
                # Prefer a pet/shared entry over a general duplicate of the same park.
                pool.sort(key=lambda p:(p['category']=='parks',distance(p,destination)))
            else:pool.sort(key=lambda p:distance(p,destination))
            for p in pool[:14]:add(p,purpose)
    meals=[]
    for p in local:
        if p['category']!='restaurants' or (p.get('restaurant_details') or {}).get('match_status')=='needs_review':continue
        if cuisine and cuisine not in (p.get('cuisines') or ['未分類']):continue
        meals.append(p)
    meals.sort(key=lambda p:distance(p,destination))
    for p in meals[:18]:add(p,'meal')
    # Bounded data for the agent; all factual data is rehydrated server-side afterward.
    return candidates[:65], parking


def group_by_parking(stops, parking):
    """Greedy set cover: first minimise parking moves, then the sum of straight-line distances."""
    remaining=list(stops);groups=[]
    while remaining:
        ranked=[]
        for carpark in parking:
            covered=[s for s in remaining if distance(s['place'],carpark) <= 1000]
            if covered:ranked.append((-len(covered),sum(distance(s['place'],carpark) for s in covered),carpark,covered))
        if not ranked:break
        _,_,carpark,covered=min(ranked,key=lambda r:(r[0],r[1],r[2]['id']))
        group_stops=[]
        for stop in covered:
            row={k:v for k,v in stop.items() if k not in ('parking_ids','anchor_distance_m','id')}
            row['distance_m']=round(distance(stop['place'],carpark),1)
            if row['place']['category']=='malls':
                row['mall_policy_summary']=' '.join(row['place'].get('notes_en') or row['place'].get('notes') or [])
            group_stops.append(row)
        groups.append({'parking':carpark,'radius_m':1000,'stops':group_stops})
        covered_ids={s['id'] for s in covered}
        remaining=[s for s in remaining if s['id'] not in covered_ids]
    # A parking cluster is not a verified road route. Preserve visit order within it, but always eat last.
    for group in groups:
        group['stops'].sort(key=lambda stop:stop['purpose']=='meal')
    groups.sort(key=lambda group:any(stop['purpose']=='meal' for stop in group['stops']))
    return groups,remaining


def prefer_single_parking(candidates, parking, destination):
    """When one car park covers every module, keep the agent inside its coverage."""
    purposes={candidate['purpose'] for candidate in candidates}
    if not purposes:return candidates
    eligible=[{p for c in candidates if c['purpose']==purpose for p in c['parking_ids']}
              for purpose in purposes]
    shared=set.intersection(*eligible)
    by_id={p['id']:p for p in parking}
    shared &= by_id.keys()
    if not shared:return candidates
    def score(park_id):
        carpark=by_id[park_id]
        total=sum(min(distance(c['place'],carpark) for c in candidates
                      if c['purpose']==purpose and park_id in c['parking_ids']) for purpose in purposes)
        return total+distance(carpark,destination)*.2, park_id
    chosen=min(shared,key=score)
    return [c for c in candidates if chosen in c['parking_ids']]


def compact_candidate(item, language):
    p=item['place'];details=p.get('restaurant_details') or {}
    name=(details.get('display_name') or p.get('name_en') or p['name']) if language=='en' else (details.get('display_name') or p['name'])
    row={'id':item['id'],'purpose':item['purpose'],'name':name,
         'parking_ids':item['parking_ids'],'distance_from_area_m':item['anchor_distance_m']}
    if item.get('activity'):row['activity']={k:item['activity'].get(k) for k in ('name','dates_text','start_date','end_date')}
    return row


async def create_plan(container, request: PlanRequest, selector=select_plan_stops):
    places=container.pets.places()['items'];activities=container.pets.activities()['items']
    parking_result=await container.parking.list(language=request.language)
    all_destinations=destinations(places,request.region)
    if not request.random:
        all_destinations+=local_areas(places,activities,request)
    if request.destination_id:
        all_destinations=[d for d in all_destinations if d['id']==request.destination_id]
        if not all_destinations:raise ValueError('The destination is not available in the selected region.')
    prepared=[]
    for destination in all_destinations:
        candidates,parking=build_candidates(places,activities,parking_result['items'],request,destination)
        purposes={c['purpose'] for c in candidates}
        required=set(request.interests)|{'meal'}
        score=(len(purposes & required),len(candidates))
        if candidates:prepared.append((score,destination,candidates,parking))
    if not prepared:
        return {'id':uuid4().hex,'status':'no_results','date':request.date.isoformat(),'region':request.region,
                'title':'No matching outing' if request.language=='en' else '暫未搵到合適行程',
                'summary':'No verified stops with a published car park within 1 km match these choices.' if request.language=='en' else '暫未有符合條件、而且距離已收錄停車場1公里內嘅地點。',
                'parking_groups':[],'map_places':[],'warnings':[],'sources':[]}
    max_coverage=max(x[0][0] for x in prepared)
    viable=[x for x in prepared if x[0][0]==max_coverage]
    if request.random:
        _,destination,candidates,parking=secrets.choice(viable)
    else:
        _,destination,candidates,parking=max(viable,key=lambda x:x[0])
    candidates=prefer_single_parking(candidates,parking,destination)
    agent_payload=request.model_dump(mode='json')
    compact=[compact_candidate(c,request.language) for c in candidates]
    async with asyncio.timeout(100):
        selected_ids=await selector(agent_payload,destination,compact,container.settings)
    by_id={c['id']:c for c in candidates};selected=[];seen=set()
    for stop_id in selected_ids:
        if stop_id not in by_id or stop_id in seen:continue
        if by_id[stop_id]['purpose']=='meal' and any(s['purpose']=='meal' for s in selected):continue
        selected.append(by_id[stop_id]);seen.add(stop_id)
    if not selected:raise ValueError('The planner did not select a valid local stop.')
    # Repair missing requested modules with existing validated candidates, never fabricate a new venue.
    required=list(dict.fromkeys(request.interests+['meal']))
    for purpose in required:
        if not any(s['purpose']==purpose for s in selected):
            candidate=next((c for c in candidates if c['purpose']==purpose and c['id'] not in seen),None)
            if candidate:selected.append(candidate);seen.add(candidate['id'])
    groups,uncovered=group_by_parking(selected,parking)
    english=request.language=='en';warnings=[]
    for purpose in required:
        if not any(s['purpose']==purpose for g in groups for s in g['stops']):
            warnings.append((f'No matching {purpose} stop with parking coverage was found.' if english else f'暫未搵到有停車場覆蓋嘅 {purpose} 地點。'))
    if request.cuisine and not any(s['purpose']=='meal' for g in groups for s in g['stops']):
        warnings.append('No matched restaurant for the selected cuisine was found in this area.' if english else '呢個區域暫未搵到符合所選菜系嘅已匹配餐廳。')
    if parking_result.get('status') not in ('ready','fresh'):
        warnings.append('Parking data may be incomplete or cached. Check its update time before departure.' if english else '停車場資料可能唔完整或來自快取，出發前請睇更新時間。')
    if any(s.get('activity') for g in groups for s in g['stops']):
        warnings.append('Activity dates are from the published listing; confirm the selected session and registration with the organiser.' if english else '活動日期按主辦方原文列出，所選場次同報名情況請向主辦方確認。')
    map_places=[];seen_places=set();sources=[{'title':destination['name_en'] if english else destination['name'],'url':destination['source_url']}]
    for group in groups:
        parking_item=group['parking'];map_places.append(parking_item)
        sources.append({'title':parking_item['name'],'url':parking_item['source_url']})
        for stop in group['stops']:
            place=stop['place']
            if place['id'] not in seen_places:map_places.append(place);seen_places.add(place['id'])
            sources.append({'title':place.get('name_en') or place['name'],'url':place['source_url']})
            if place['category']=='malls':
                stop['mall_policy_summary']=' '.join((place.get('notes_en') if english else place.get('notes')) or place.get('notes') or [])
    names=[]
    for group in groups:
        names.extend((s['place'].get('name_en') or s['place']['name']) if english else s['place']['name'] for s in group['stops'])
    area_name=destination['name_en'] if english else destination['name']
    # A local venue is a search anchor, not a guaranteed visit. Name the outing
    # after an included stop when the final parking groups omit that venue.
    if destination['id'].startswith('area:') and not seen_places.intersection(destination['anchor_place_ids']) and names:
        area_name=names[0]
    summary=(f"Explore {area_name}: "+' → '.join(names)+f'. Use {len(groups)} parking stop(s); every included place is within 1 km of its assigned car park (straight-line).'
             if english else f"{area_name}行程："+' → '.join(names)+f'。使用{len(groups)}個停車點，每個地點距離所屬停車場直線1公里內。')
    return {'id':uuid4().hex,'status':'partial' if warnings else 'ready','date':request.date.isoformat(),
            'region':request.region,'destination':destination,'title':area_name+(' pet outing' if english else '攜寵遊'),
            'summary':summary,'parking_groups':groups,'map_places':map_places,'warnings':warnings,
            'sources':list({s['url']:s for s in sources}.values()),'model':container.settings.model}
