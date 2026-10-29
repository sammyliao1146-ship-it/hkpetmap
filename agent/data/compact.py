"""Small, sourced model inputs. Full records remain available to application APIs."""
import copy


def place_for_agent(place, *, reviews=False):
    if place is None:
        return None
    keep=('id','category','name','name_en','district','address','address_en','latitude','longitude',
          'cuisines','cuisine_source','telephone','opening_hours','opening_hours_en','website','website_en',
          'pet_policy','notes','notes_en','rules_url','rules_url_en','source_url','source_name',
          'source_updated_at','mall_policy','distance_m')
    result={k:copy.deepcopy(place[k]) for k in keep if k in place}
    details=place.get('restaurant_details')
    if details:
        keys=('google_place_id','display_name','google_address','match_status','rating','rating_count',
              'price_level','price_range','website','telephone','hours','reservable','booking_url','menu_url',
              'google_maps_url','reviews_url','fetched_at')
        result['restaurant_details']={k:copy.deepcopy(details[k]) for k in keys if k in details}
        if reviews:
            result['restaurant_details']['reviews']=[{k:(v[:500] if isinstance(v,str) and k in ('text','original_text') else v)
                for k,v in r.items()} for r in details.get('reviews',[])[:2]]
    return result


def sources_for_places(items):
    return list({p['source_url']:{'url':p['source_url'],'title':p.get('source_name','')}
                 for p in items if p.get('source_url')}.values())
