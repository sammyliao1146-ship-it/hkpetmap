"""Deterministic nearby answer built from the featured-restaurant DB (no model call)."""
import re

_EN_FILLER={'find','me','a','an','the','some','please','pls','recommend','show','search','restaurant','restaurants','place',
              'places','eat','food','dog','dogs','friendly','pet','petfriendly','near','nearby','nearest','closest','to','my',
              'location','here','i','want','where','can','get','any','good','is','are','there','what','around','you','of','for','in','us','and'}
_ZH_FILLER=('狗友善','寵物友善','附近','最近','近啲','近少少','搵','找','餐廳','食肆','有咩','有冇','邊度','邊間','幫我','我想','推介','推薦','請','呢度','啲','嘅','嗎','吗','食','飯','間','狗','可以','一下','下','附近有','有')


def is_simple_nearby(message:str)->bool:
    """True only for plain "restaurants near me" requests with no extra condition (cuisine, price, rating...)."""
    text = message.strip().lower()
    if not text or len(text) > 60:
        return False
    if not re.search(r'near|closest|nearest|附近|最近|近啲|近少少|close|nearby|最近', text) or not re.search(r'restaurant|eat|food|餐廳|食肆|食|飯|dining|rest aurant|餐厅', text):
        return False
    for token in _ZH_FILLER:
        text = text.replace(token, ' ')
    words = re.findall(r"[a-z]+|[\u4e00-\u9fff]+", text.replace('-', ''))
    return all(w in _EN_FILLER for w in words)


def _price(r, en):
    lo, hi = r.get('price_min'), r['price_max']
    span = f'HK${lo:.0f}–{hi:.0f}' if lo is not None and lo != hi else f'HK${hi:.0f}'
    return f'{span} per person (Google estimate)' if en else f'人均 {span}（Google 估算）'


def render_nearby(rows: list[dict], language: str) -> str:
    en=language=='en'
    if not rows:
        return ('I have no featured restaurants to rank for your location yet.' if en else '暫時未有精選餐廳可按你嘅位置排序。')
    lines = ['**Nearest featured dog-friendly restaurants** (high rating, reasonable price, straight-line distance):' if en
             else '**離你最近嘅精選狗友善餐廳**（評分高、價錢合理，按直線距離排序）：', '']
    for i, r in enumerate(rows, 1):
        name = (r['name_en'] or r['name']) if en else r['name']
        address = (r.get('address_en') or r.get('address')) if en else (r.get('address') or r.get('address_en'))
        km = r['distance_m'] / 1000
        head = f"{i}. **{name}** · {km:.2f} km · ⭐ {r['rating']:.1f} ({r['rating_count']}) · {r['cuisine']}"
        lines.append(f"{head}\n   {_price(r, en)}" + (f"\n   {address}" if address else ''))
    lines += ['', ('Straight-line distance, not walking time. This is a curated shortlist, not every restaurant on the map; '
                   'ratings and prices are saved Google data, so check opening hours and dog-entry rules with the venue.' if en else
                   '距離係直線距離，唔係步行時間。呢個係精選名單，唔係地圖上全部餐廳；評分同價錢係已儲存嘅 Google 資料，入場同營業時間請向餐廳確認。')]
    return '\n'.join(lines)
