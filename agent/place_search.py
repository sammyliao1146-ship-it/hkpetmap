"""使用球面距离公式计算"""
import math
import random

SORT_MODES={'default','distance','rating','random'}

def valid_origin(latitude,longitude):
    if latitude is None or longitude is None:
        raise ValueError('Provide both origin latitude and longitude')
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90<=latitude<=90 or not -180<=longitude<=180:
        raise ValueError('Invalid origin coordinates')
    return float(latitude),float(longitude)

def distance_m(origin,latitude,longitude):
    a,b=math.radians(origin[0]),math.radians(latitude)
    h=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(math.radians(longitude-origin[1])/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))

def price_ceiling(profile):
    """Upper HKD price per person from the stored Google price range, or None when unpriced."""
    rng=profile.get('price_range') or {}
    for key in ('endPrice','startPrice'):
        try:
            value=float((rng.get(key) or {}).get('units'))
        except (TypeError,ValueError):continue
        if math.isfinite(value):return value
    return None

def select_places(data,*,sort_by='default',origin=None,radius_m=None,min_rating=None,limit=8,max_price=None):
    if sort_by not in SORT_MODES:
        raise ValueError('Unsupported sort_by')
    if not 1<=limit<=20:
        raise ValueError('limit must be 1–20')
    if radius_m is not None and (not math.isfinite(radius_m) or not 0<radius_m<=100000):
        raise ValueError('radius_m must be in (0, 100000]')
    if min_rating is not None and (not math.isfinite(min_rating) or not 0<=min_rating<=5):
        raise ValueError('min_rating must be in [0, 5]')
    if max_price is not None and (not math.isfinite(max_price) or max_price<=0):
        raise ValueError('max_price must be a positive HKD amount')
    if origin is not None:origin=valid_origin(*origin)
    meta={'sort_by':sort_by,'filtered_total':len(data['items']),'distance_type':'straight_line' if origin else None,
          'origin':{'latitude':origin[0],'longitude':origin[1]} if origin else None,'radius_m':radius_m,'min_rating':min_rating,'max_price_hkd':max_price}
    if (sort_by=='distance' or radius_m is not None) and origin is None:
        return {**data,**meta,'items':[],'total':0,'mapped':0,'returned':0,'truncated':False,'query_status':'needs_location',
                'message':'Provide explicitly shared coordinates, or an existing map place as origin. No distance can be inferred from chat text alone.'}
    rows=[];missing_coordinates=0;missing_ratings=0;unpriced=0
    for original in data['items']:
        p=dict(original);profile=p.get('restaurant_details') or {};rating=profile.get('rating')
        has_rating=isinstance(rating,(int,float)) and math.isfinite(rating) and 0<=rating<=5
        if not has_rating:missing_ratings+=1
        if (sort_by=='rating' or min_rating is not None) and not has_rating:continue
        if min_rating is not None and rating<min_rating:continue
        if max_price is not None:
            ceiling=price_ceiling(profile)
            if ceiling is None:unpriced+=1;continue
            if ceiling>max_price:continue
        meters=None
        if origin:
            lat,lon=p.get('latitude'),p.get('longitude')
            if lat is None or lon is None:
                missing_coordinates+=1
                if sort_by=='distance' or radius_m is not None:continue
            else:
                meters=distance_m(origin,lat,lon)
                if radius_m is not None and meters>radius_m:continue
                p['distance_m']=round(meters,1)
        rows.append((p,meters))
    if sort_by=='distance':rows.sort(key=lambda r:(r[1],r[0]['id']))
    elif sort_by=='rating':rows.sort(key=lambda r:(-(r[0]['restaurant_details']['rating']),-(r[0]['restaurant_details'].get('rating_count') or 0),r[0]['id']))
    total=len(rows);mapped=sum(r[0].get('latitude') is not None and r[0].get('longitude') is not None for r in rows)
    if sort_by=='random':chosen=random.SystemRandom().sample(rows,min(limit,total))
    else:chosen=rows[:limit]
    return {**data,**meta,'items':[r[0] for r in chosen],'total':total,'mapped':mapped,'returned':len(chosen),'truncated':total>limit,
            'query_status':'ready','excluded_without_price':unpriced,'missing_coordinates':missing_coordinates,'missing_ratings':missing_ratings,
            'ranking':'rating_desc_then_rating_count_desc' if sort_by=='rating' else sort_by}
