"""Strict, single-field saved-data lookups; complex/current questions stay with the Agent."""
import re
from urllib.parse import urlsplit


def saved_lookup(message, history, access, language):
    text = message.strip().rstrip('?？').strip()
    match = re.fullmatch(r"(?:what is (?:the )?)?(phone(?: number)?|telephone|website)(?: of| for)? (.+)", text, re.I)
    if match:
        field, target = match.groups()
        field = 'website' if field.lower() == 'website' else 'telephone'
    else:
        match = re.fullmatch(r'(.+?)(?:嘅|的)?(電話|電話號碼|官網|官方網站)', text)
        if not match:
            return None
        target, field = match.groups()
        field = 'website' if field in {'官網', '官方網站'} else 'telephone'
    target = target.strip().rstrip('嘅的').strip()
    recent = access.recent_places(history)
    if target.casefold() in {'it', 'its', 'that restaurant', '佢', '它', '嗰間', '這家餐廳', '呢間'}:
        ids = [p['id'] for p in recent] if len(recent) == 1 else []
    else:
        ids = [p.id for p in (access.pets.snapshot.places if access.pets.snapshot else [])
               if target.casefold() in {n.casefold() for n in (p.name, p.name_en,
                   p.restaurant_details.display_name if p.restaurant_details else None) if n}]
    if len(ids) != 1:
        return None
    p = access.pets.place(ids[0])
    value = (p.get('restaurant_details') or {}).get(field) or p.get(field)
    if not value:
        return None
    if field == 'website' and urlsplit(value).scheme not in {'http', 'https'}:
        return None
    name = (p.get('name_en') or p['name']) if language == 'en' else ((p.get('restaurant_details') or {}).get('display_name') or p['name'])
    label = ('Website' if field == 'website' else 'Phone') if language == 'en' else ('官網' if field == 'website' else '電話')
    rendered = f'[{label}]({value})' if field == 'website' else value
    note = 'Saved map data; please confirm with the venue.' if language == 'en' else '以上係已儲存嘅地圖資料，請向場地確認。'
    return {'answer':f'{name} · {label}: {rendered}\n\n{note}', 'places':[{'id':p['id'], 'name':name}],
            'sources':[{'title':p.get('source_name') or name, 'url':p['source_url']}] if p.get('source_url') else []}
