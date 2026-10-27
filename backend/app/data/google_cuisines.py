"""Read saved Google categories only. No Google calls or automatic refresh."""
import json
import logging
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from pydantic import HttpUrl

ROOT=Path(__file__).resolve().parents[3]
MANIFEST=ROOT/'data/google-places/cuisine-map.json'
EXTRA_CUISINES={'法式':'French','台式':'Taiwanese','印度／中東':'Indian / Middle Eastern','墨西哥／拉美':'Mexican / Latin American','海鮮':'Seafood','酒吧／燒烤':'Bars / Grills','其他餐廳':'Other restaurants'}
TYPE_CUISINES={
 '咖啡／輕食':'cafe coffee_shop cat_cafe tea_house sandwich_shop deli brunch_restaurant coffee_stand',
 '中式':'chinese_restaurant chinese_noodle_restaurant dumpling_restaurant hot_pot_restaurant',
 '港式':'cantonese_restaurant dim_sum_restaurant hong_kong_style_fast_food_restaurant',
 '日式':'japanese_restaurant ramen_restaurant sushi_restaurant tonkatsu_restaurant yakitori_restaurant japanese_izakaya_restaurant yakiniku_restaurant',
 '韓式':'korean_restaurant korean_barbecue_restaurant',
 '西式':'western_restaurant american_restaurant steak_house hamburger_restaurant bistro european_restaurant irish_restaurant spanish_restaurant greek_restaurant german_restaurant australian_restaurant fish_and_chips_restaurant',
 '意式／薄餅':'italian_restaurant pizza_restaurant', '法式':'french_restaurant',
 '泰式':'thai_restaurant', '越式':'vietnamese_restaurant','台式':'taiwanese_restaurant',
 '印度／中東':'indian_restaurant pakistani_restaurant middle_eastern_restaurant turkish_restaurant lebanese_restaurant',
 '墨西哥／拉美':'mexican_restaurant tex_mex_restaurant latin_american_restaurant brazilian_restaurant',
 '海鮮':'seafood_restaurant oyster_bar_restaurant',
 '酒吧／燒烤':'bar barbecue_restaurant bar_and_grill pub wine_bar cocktail_bar lounge_bar sports_bar gastropub irish_pub',
 '甜品':'dessert_shop dessert_restaurant bakery ice_cream_shop cake_shop chocolate_shop',
 '素食':'vegetarian_restaurant vegan_restaurant',
}
TYPE_LABELS={t:label for label,types in TYPE_CUISINES.items() for t in types.split()}
GENERIC={'restaurant','fast_food_restaurant','asian_restaurant','asian_fusion_restaurant','fusion_restaurant','fine_dining_restaurant','buffet_restaurant','food_court','chicken_restaurant','snack_bar','malaysian_restaurant','hawaiian_restaurant'}
def cuisine(details):
    primary=details.get('primaryType')
    if primary in TYPE_LABELS: return TYPE_LABELS[primary]
    # A hotel/mall/sports venue may list restaurant as an amenity; do not borrow
    # its classification, reviews or photographs for a tenant restaurant.
    if primary not in GENERIC | {'food_store','store','banquet_hall',None}: return None
    for t in details.get('types',[]):
        if t in TYPE_LABELS: return TYPE_LABELS[t]
    return '其他餐廳' if primary in GENERIC else None

# Address-reviewed matches: exact source address plus fixed candidate ID.
# Re-evaluate rather than retaining an override if either address changes.
REVIEWED_PATH=Path(__file__).with_name('reviewed_restaurant_matches.json')
def reviewed_match(place,record,meters):
    try: overrides=json.loads(REVIEWED_PATH.read_text())
    except (OSError,ValueError): return None
    row=overrides.get(place.id)
    d=record.get('details') or {}
    if (not row or row['google_place_id']!=record.get('google_place_id')
            or row['source_address']!=place.address
            or row['google_address']!=d.get('formattedAddress')
            or meters is None or meters>row['max_distance_m']): return None
    return row['evidence']

def normalized(value):
    return re.sub(r'[^\w\u3400-\u9fff]','',unicodedata.normalize('NFKC',value or '').casefold())
def similarity(place,details):
    name=normalized(details.get('displayName',{}).get('text'))
    scores=[]
    for value in (place.name,place.name_en):
        source=normalized(value)
        if not name or not source: continue
        score=SequenceMatcher(None,source,name).ratio()
        if min(len(source),len(name))>=3 and (source in name or name in source): score=max(score,.9)
        scores.append(score)
    return max(scores,default=0)
def distance(place,details):
    location=details.get('location',{})
    if place.latitude is None or place.longitude is None or not location: return None
    a,b=math.radians(place.latitude),math.radians(location['latitude'])
    dlat=b-a;dlon=math.radians(location['longitude']-place.longitude)
    h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))
def select_candidate(place,records):
    matches=[]
    for record in records:
        d=record.get('details') or {};label=cuisine(d)
        if not label or record.get('status')!='ready': continue
        sim=similarity(place,d);meters=distance(place,d)
        evidence=reviewed_match(place,record,meters)
        accepted=bool(evidence) or (meters is not None and ((meters<=120 and sim>=.48) or (meters<=300 and sim>=.85))) or (meters is None and sim>=.9)
        if not accepted: continue
        score=(2 if evidence else 0)+sim+(.25*(1-min(meters,300)/300) if meters is not None else 0)
        matches.append((score,record,label,sim,meters,evidence))
    matches.sort(key=lambda item:item[0],reverse=True)
    if not matches or (len(matches)>1 and matches[0][0]-matches[1][0]<.12): return None
    _,record,label,sim,meters,evidence=matches[0]
    pid=record['google_place_id']
    return {'google_place_id':pid,'cuisines':[label],'source_url':record['details'].get('googleMapsUri') or f'https://www.google.com/maps/search/?api=1&query=restaurant&query_place_id={pid}','match_method':'address_reviewed' if evidence else 'name_and_distance','match_evidence':evidence,'name_similarity':round(sim,3),'distance_m':round(meters,1) if meters is not None else None}
def select_cuisine_candidate(place,records):
    """User-requested relaxed inclusion: cuisine is enough; retain review status."""
    ranked=[]
    for rank,record in enumerate(records):
        if record.get('status')!='ready': continue
        d=record.get('details') or {}
        label=cuisine(d)
        if not label:
            label=next((TYPE_LABELS[t] for t in d.get('types',[]) if t in TYPE_LABELS),None)
        if not label: continue
        sim=similarity(place,d);meters=distance(place,d)
        score=.4*sim+(.6/(1+meters/500) if meters is not None else 0)-rank*.001
        ranked.append((score,record,label,sim,meters))
    if not ranked:return None
    _,record,label,sim,meters=max(ranked,key=lambda r:r[0]);d=record['details'];pid=record['google_place_id']
    return {'google_place_id':pid,'cuisines':[label],
        'source_url':d.get('googleMapsUri') or f'https://www.google.com/maps/search/?api=1&query=restaurant&query_place_id={pid}',
        'match_method':'cuisine_candidate','match_status':'needs_review',
        'match_evidence':'Included by saved Google cuisine without name/distance threshold; candidate identity remains unverified.',
        'name_similarity':round(sim,3),'distance_m':round(meters,1) if meters is not None else None}

def attach_google_cuisines(places,path=None):
    manifest=Path(path) if path else MANIFEST
    if not manifest.exists(): return
    try: rows=json.loads(manifest.read_text())['restaurants']
    except (OSError,ValueError,KeyError):
        logging.getLogger(__name__).warning('Cannot read local cuisine map');return
    for p in places:
        if p.category!='restaurants': continue
        from urllib.parse import urlparse
        google_source=urlparse(str(p.cuisine_source or '')).hostname in {'maps.google.com','www.google.com'}
        if p.cuisines and not google_source: continue # Keep sourced curated labels.
        if google_source:
            p.cuisines=[];p.cuisine_source=None # Drop obsolete derived labels from cached snapshots.
        row=rows.get(p.id)
        if row and row.get('address')==p.address and row.get('cuisines'):
            p.cuisines=row['cuisines'];p.cuisine_source=HttpUrl(row['source_url'])
