"""Render a validated structured outing as chat without another generation/review round."""
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from backend.app.cache.place_queries import canonical_district
from backend.app.data.geography import DISTRICTS, REGIONS
from backend.app.data.sources import CUISINES
from backend.app.models.assistant import ChatResponse
from backend.app.models.plan import PlanRequest
from backend.app.services.outing_plan import CUISINE_ALIASES, create_plan
from backend.app.observability.trace import current_trace


def name(place, english):
    return ((place.get('name_en') or place['name']) if english else
            ((place.get('restaurant_details') or {}).get('display_name') or place['name']))


def sourced_label(label, url):
    # Saved names/URLs remain data. The UI only links safe, supplied source URLs.
    label=str(label).replace('[','(').replace(']',')').replace('\n',' ')
    parsed=urlparse(str(url or ''))
    return f'[{label}]({url})' if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password else label


def render_plan(plan, language, *, assumed_date=False):
    english=language=='en'
    lines=[plan['title'],plan['summary']]
    if assumed_date:
        lines.append((f"No date was specified; this plan uses {plan['date']}. Opening hours have not been checked."
                      if english else f"未指定日期，暫按 {plan['date']} 規劃；未核實當日營業時間。"))
    elif plan.get('date'):
        lines.append(('Date: ' if english else '日期：')+plan['date'])
    for group in plan['parking_groups']:
        park=group['parking']
        lines.append(('Park at: ' if english else '停車點：')+sourced_label(name(park,english),park.get('source_url')))
        for index,stop in enumerate(group['stops'],1):
            p=stop['place'];details=p.get('restaurant_details') or {}
            line=f"{index}. "+sourced_label(name(p,english),p.get('source_url'))
            line+=f" · {stop['distance_m']:g} m "+('from this car park' if english else '距離此停車場')
            if details.get('rating') is not None:
                line+=f" · ★ {details['rating']:g} "+('(saved Google rating)' if english else '（已儲存 Google 評分）')
            lines.append(line)
            address=(p.get('address_en') or p.get('address')) if english else p.get('address')
            if address:lines.append(str(address))
            if p['category']=='malls':
                policy=stop.get('mall_policy_summary')
                lines.append(policy or ('Confirm pet-access areas and carrier/stroller rules with the mall.' if english else '請向商場確認可攜寵範圍及車／袋要求。'))
                if (p.get('mall_policy') or {}).get('verification')=='third_party':
                    lines.append('Third-party directory listing; confirm with the mall and individual shops.' if english else '第三方目錄資料，請向商場及個別店舖確認。')
            if stop.get('activity'):
                a=stop['activity']
                values=[a.get(k) for k in ('dates_text','fees','registration_url') if a.get(k)]
                if values:lines.append(' · '.join(map(str,values)))
    lines.extend(plan.get('warnings') or [])
    if plan['parking_groups']:
        lines.append('Distances are straight-line, not verified walking routes. Confirm opening hours and current venue rules before visiting.' if english else '以上為直線距離，唔係已核實步行路線；出發前請確認營業時間同最新場地規則。')
    return '\n\n'.join(lines)


async def chat_plan(payload, container, decision, routing):
    preferences=getattr(decision,'plan',None)
    def record_route(reason):
        if trace:=current_trace.get():
            span=trace.start('planning','plan_preferences')
            span['route_reason']=reason
            span['preferences']=preferences.model_dump(mode='json') if preferences else None
            trace.end(span)
    if preferences is None or preferences.unsupported_constraints:
        record_route('missing_preferences' if preferences is None else 'unsupported_constraints')
        return None
    district=canonical_district(preferences.district)
    # Unrecognised neighbourhoods/specific venues retain the general Agent path.
    if district and district not in set(DISTRICTS.values())|set(REGIONS):
        record_route('unrecognised_district')
        return None
    cuisine=CUISINE_ALIASES.get(preferences.cuisine.strip().lower(),preferences.cuisine.strip())
    if cuisine and cuisine not in CUISINES:
        record_route('unrecognised_cuisine')
        return None
    record_route('structured_plan')
    request=PlanRequest(date=preferences.date or datetime.now(ZoneInfo('Asia/Hong_Kong')).date(),
                        region=preferences.region,district=district,
                        interests=preferences.interests if preferences.interests is not None else ['park'],
                        cuisine=cuisine,random=preferences.random,destination_id=preferences.destination_id,
                        origin=payload.origin,language=payload.language)
    plan=await create_plan(container,request)
    return ChatResponse(answer=render_plan(plan,payload.language,assumed_date=preferences.date is None),
                        model=plan.get('model') or 'saved-data',routing=routing,sources=plan['sources'],
                        places=[{'id':p['id'],'name':name(p,payload.language=='en')} for p in plan['map_places']])
