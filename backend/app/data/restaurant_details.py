"""Attach frozen local restaurant details; never call external services."""
import json
from pathlib import Path
from backend.app.data.google_cuisines import ROOT, MANIFEST
from backend.app.models.pet import RestaurantDetails
BASE=ROOT/'data/google-places'

def photo_path(pid,base=None):
    import re
    base=Path(base) if base else BASE
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,200}',pid): return None
    try:
        record=json.loads((base/'places'/f'{pid}.json').read_text())
        photo=record.get('photo') or {}
        if photo.get('status')!='ready' or not photo.get('local_path'): return None
        path=(base/photo['local_path']).resolve()
        if not path.is_relative_to((base/'photos').resolve()) or not path.is_file(): return None
        return path
    except (ValueError,OSError,TypeError): return None

DISH_MANIFEST=BASE/'dish-photos/selected.json'
def dish_photo_path(pid,base=None):
    import re
    base=Path(base) if base else BASE
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,200}',pid):return None
    try:
        row=json.loads((base/'dish-photos/selected.json').read_text())['places'].get(pid)
        if not row or row.get('visual_review') not in {'food','drink'}:return None
        path=(base/row['local_path']).resolve()
        if not path.is_relative_to((base/'dish-photos').resolve()) or not path.is_file():return None
        return path
    except (OSError,ValueError,KeyError,TypeError):return None

def attach_restaurant_details(places,manifest=None,base=None):
    base=Path(base) if base else BASE
    path=Path(manifest) if manifest else MANIFEST
    try: matches=json.loads(path.read_text())['restaurants']
    except (OSError,ValueError,KeyError): return
    try: dishes=json.loads((base/'dish-photos/selected.json').read_text())['places']
    except (OSError,ValueError,KeyError):dishes={}
    for p in places:
        if p.category!='restaurants': continue
        p.restaurant_details=None
        match=matches.get(p.id)
        if not match or match.get('address')!=p.address: continue
        pid=match['google_place_id']
        # Never trust a path embedded in the candidate index.
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{5,200}',pid): continue
        try:
            record=json.loads((base/'places'/f'{pid}.json').read_text())
            if record.get('status')!='ready': continue
            dish=dishes.get(pid,{}) if dish_photo_path(pid,base) else {}
            dish_meta=dish.get('metadata',{})
            dish_authors=dish_meta.get('authorAttributions',[])
            d=record['details'];photo=record.get('photo') or {};meta=photo.get('metadata') or {}
            authors=meta.get('authorAttributions') or []
            reviews=[]
            for r in d.get('reviews',[]):
                author=r.get('authorAttribution') or {}
                reviews.append({'author':author.get('displayName','Google user'),'author_url':author.get('uri'),'rating':r.get('rating'),'text':r.get('text',{}).get('text'),'original_text':r.get('originalText',{}).get('text'),'original_language':r.get('originalText',{}).get('languageCode'),'published_at':r.get('publishTime'),'url':r.get('googleMapsUri')})
            p.restaurant_details=RestaurantDetails(
                google_place_id=pid,display_name=d.get('displayName',{}).get('text'),
                display_name_language=d.get('displayName',{}).get('languageCode'),google_address=d.get('formattedAddress'),
                match_status=match.get('match_status','matched'),match_distance_m=match.get('distance_m'),rating=d.get('rating'),rating_count=d.get('userRatingCount'),price_level=d.get('priceLevel'),price_range=d.get('priceRange'),
                website=d.get('websiteUri'),telephone=d.get('nationalPhoneNumber') or d.get('internationalPhoneNumber'),
                hours=d.get('regularOpeningHours',{}).get('weekdayDescriptions',[]),reservable=d.get('reservable'),booking_url=record.get('booking_url'),menu_url=record.get('menu_url'),
                google_maps_url=d.get('googleMapsUri'),reviews_url=d.get('googleMapsLinks',{}).get('reviewsUri'),reviews=reviews,
                photo_url=f'/api/v1/restaurant-photos/{pid}' if photo_path(pid,base) else None,
                photo_source_url=meta.get('googleMapsUri') or d.get('googleMapsUri'),photo_credit=' / '.join(a.get('displayName','') for a in authors) or 'Google Maps',photo_authors=authors,
                dish_photo_url=f'/api/v1/restaurant-dish-photos/{pid}' if dish else None,
                dish_photo_source_url=dish_meta.get('googleMapsUri') if dish else None,
                dish_photo_credit=' / '.join(a.get('displayName','') for a in dish_authors) or 'Google Maps' if dish else None,
                dish_photo_kind=dish.get('visual_review'),fetched_at=record.get('fetched_at'))
        except (OSError,ValueError,KeyError,TypeError): continue
