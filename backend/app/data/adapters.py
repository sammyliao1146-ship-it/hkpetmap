"""Read public source documents. No Google-derived content or private booking APIs."""
import hashlib
import io
import json
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.app.data.sources import FEHD_URL, HOTEL_URL, SPCA_URL, VET_URL, Layer
from backend.app.models.pet import Activity, Place


def text(value):
    if value is None:
        return None
    raw = str(value)
    result = BeautifulSoup(raw, 'html.parser').get_text(' ', strip=True) if '<' in raw else raw.strip()
    return result if result.casefold() not in {'', 'n.a.', 'n/a', 'null', '-'} else None


def safe_url(value, base=''):
    url = urljoin(base, value or '')
    p = urlparse(url)
    return url if p.scheme == 'https' and p.hostname and not p.username and not p.password else None


def identity(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16]


async def arcgis(client: httpx.AsyncClient, layer: Layer, where='1=1'):
    result, seen, offset = [], set(), 0
    for _ in range(100):
        response = await client.get(layer.url, params={'where': where, 'outFields': '*', 'outSR': 4326,
            'f': 'geojson', 'resultRecordCount': 1000, 'resultOffset': offset, 'orderByFields': 'OBJECTID ASC'})
        response.raise_for_status()
        page = response.json()
        if page.get('type') != 'FeatureCollection':
            raise ValueError('CSDI 未有傳回有效圖層')
        features = page.get('features', [])
        before = len(seen)
        for feature in features:
            rid = str(feature.get('id') or feature.get('properties', {}).get('OBJECTID'))
            if rid not in seen:
                result.append(feature)
                seen.add(rid)
        if not (page.get('exceededTransferLimit') or page.get('properties', {}).get('exceededTransferLimit')):
            return result
        if not features or len(seen) == before:
            raise ValueError('CSDI 分頁未有前進')
        offset += len(features)
    raise ValueError('CSDI 分頁超出安全上限')


def normalize_layer(layer: Layer, feature):
    p = feature['properties']
    def pick(*keys):
        return next((v for k in keys if (v := text(p.get(k)))), None)
    name = pick('NameTC', 'NAME_TC', 'Address_CHI__', 'NameEN')
    lon, lat = feature['geometry']['coordinates'][:2]
    if not name or feature['geometry']['type'] != 'Point':
        raise ValueError('Missing name or point')
    notes = [v for v in [pick('FacilityDetailsTC', 'Remark')] if v]
    if layer.category == 'parks':
        notes.append('一般公園資料唔代表准許帶寵物，出發前請核實場內告示。')
    if layer.category == 'inclusive_parks':
        notes.append('只限指定範圍；請遵守牽繩及場地守則。')
    return Place(id=f'{layer.key}:{p["OBJECTID"]}', category=layer.category, name=name,
        name_en=pick('NameEN', 'NAME_EN', 'Address_EN__'), address=pick('AddressTC', 'ADDRESS_TC', 'Address_CHI__'),
        address_en=pick('AddressEN', 'ADDRESS_EN'), district=pick('DistrictTC', 'SEARCH01_TC'),
        latitude=lat, longitude=lon, coordinate_source=layer.url, source_url=layer.url,
        source_name='康文署／CSDI' if layer.category != 'management' else '漁護署／CSDI',
        website=safe_url(pick('WebsiteTC', 'WebsiteEN')), website_en=safe_url(pick('WebsiteEN')), telephone=pick('TelephoneTC', 'TEL_'),
        opening_hours=pick('OpeningHoursTC', 'Operating_Hours'), opening_hours_en=pick('OpeningHoursEN'),
        notes_en=[v for v in [pick('FacilityDetailsEN')] if v], pet_policy=layer.policy, notes=notes)


def normalize_restaurants(rows, coordinates):
    if not isinstance(rows, list) or not rows:
        raise ValueError('食環署餐廳名單格式有變，保留上一份快照')
    points = {str(f['properties'].get('SEARCH02_TC')): f for f in coordinates}
    result = []
    for row in rows:
        licence = str(row.get('licence', ''))
        name = text(row.get('shop_sign_tc')) or text(row.get('shop_sign_en'))
        if not name or not re.fullmatch(r'\d{10}', licence):
            raise ValueError('食環署記錄缺少名稱或牌照號碼')
        feature = points.get(licence)
        point = feature.get('geometry', {}) if feature else {}
        coords = point.get('coordinates') if point.get('type') == 'Point' else None
        if coords and not (113.8 <= coords[0] <= 114.5 and 22.1 <= coords[1] <= 22.6):
            coords = None
        result.append(Place(id=f'restaurant:{licence}', category='restaurants', name=name,
            name_en=text(row.get('shop_sign_en')), district=text(row.get('district_tc')),
            address=text(row.get('address_tc')), address_en=text(row.get('address_en')),
            longitude=coords[0] if coords else None, latitude=coords[1] if coords else None,
            coordinate_source='食環署食肆牌照 CSDI，按牌照號碼配對' if coords else None,
            source_url=FEHD_URL, source_name='食環署：獲准許狗隻進入嘅食肆名單',
            licence_number=licence, pet_policy='dogs_permitted',
            rules_url=safe_url(row.get('house_rule_tc') or row.get('house_rule_en'), FEHD_URL) if row.get('house_rule_tc') or row.get('house_rule_en') else None,
            rules_url_en=safe_url(row.get('house_rule_en'), FEHD_URL) if row.get('house_rule_en') else None,
            notes=['准許狗隻進入唔代表接受其他寵物，入場條件以餐廳守則為準。']))
    return result


def normalize_hotels(script):
    match = re.search(r'var\s+pet_hotel_data\s*=\s*({.*})\s*;?\s*$', script, re.S)
    if not match:
        raise ValueError('漁護署寄養所資料格式有變')
    rows = json.loads(match[1])['data']
    result = []
    for r in rows:
        if r.get('ph_enable') != 'Y':
            continue
        lat, lon = r.get('ph_x_coordinate'), r.get('ph_y_coordinate')
        try:
            lat, lon = float(lat), float(lon)
            if not (22.1 <= lat <= 22.6 and 113.8 <= lon <= 114.5):
                lat = lon = None
        except (TypeError, ValueError):
            lat = lon = None
        result.append(Place(id=f'hotel:{r["ph_id"]}', category='hotels', name=text(r['ph_name_tc']) or r['ph_name_en'],
            name_en=text(r['ph_name_en']), district={'12':'中西區','13':'灣仔區','14':'東區','15':'南區','16':'油尖旺區','17':'深水埗區','18':'九龍城區','19':'黃大仙區','20':'觀塘區','21':'葵青區','22':'荃灣區','23':'屯門區','24':'元朗區','25':'北區','26':'大埔區','27':'沙田區','28':'西貢區','29':'離島區'}.get(r.get('ph_district')), address=text(r['ph_address_tc']), address_en=text(r['ph_address_en']),
            latitude=lat, longitude=lon, coordinate_source=HOTEL_URL if lat else None,
            telephone=text(r.get('ph_phone')), source_url=HOTEL_URL, source_name='漁護署持牌動物寄養所名單',
            source_updated_at=r.get('ph_update_date'), pet_policy='boarding',
            notes=['只包括同意公開資料嘅持牌寄養所，唔係全港完整名單。', '價格、可接待動物同房位請直接向寄養所查詢。']))
    if not result:
        raise ValueError('寄養所解析結果為空')
    return result


def parse_vets(body: bytes, source_url: str):
    """AFCD's landscape PDF has horizontal record borders and fixed text columns."""
    import pdfplumber
    result = []
    with pdfplumber.open(io.BytesIO(body)) as document:
        for page in document.pages:
            district = None
            settings = {'vertical_strategy':'explicit',
                        'explicit_vertical_lines':[page.width*.0402, page.width*.405, page.width*.82, page.width*.9312],
                        'horizontal_strategy':'lines'}
            revision = re.search(r'Last Revision Date:\s*(\d{2}/\d{2}/\d{4})', page.extract_text() or '')
            for table in page.extract_tables(settings):
                for cells in table:
                    if len(cells) != 3:
                        continue
                    left, address, phone = [c or '' for c in cells]
                    district_match = re.search(r'([\u4e00-\u9fff]{1,5}區)', left)
                    if district_match and 'District' in left and not re.search(r'\d{4}\s*\d{4}', phone):
                        district = district_match[1]
                    if not re.search(r'\d{4}\s*\d{4}', phone) or 'Business Address' in address:
                        continue
                    names = [s.strip() for s in left.splitlines() if s.strip()]
                    addresses = [s.strip() for s in address.splitlines() if s.strip()]
                    if not names or not addresses or '請注意' in left:
                        continue
                    result.append(Place(id='vet:'+identity('|'.join(names+addresses)), category='vets',
                        name=names[0], name_en=' '.join(names[1:]) or None, district=district, address=addresses[0],
                        address_en=' '.join(addresses[1:]) or None, telephone=' / '.join(re.findall(r'\d{4}\s*\d{4}', phone)),
                        source_url=source_url, source_name='漁護署獸醫診所名單', pet_policy='veterinary',
                        source_updated_at=revision[1] if revision else None,
                        notes=['自願列入嘅診所名錄，唔係醫院牌照認證。', '急症服務、營業時間同接受動物種類請先致電核實。']))
    if not result:
        raise ValueError('獸醫 PDF 未能解析，唔會用空清單覆蓋舊資料')
    return result


COURSE_LABELS = {'Puppy Socialization Course': '幼犬社交班', 'Large Dog Basic Obedience Course': '大型狗基本服從班',
    'Small Dog Basic Obedience Course': '小型狗基本服從班', 'Beginner Dog Agility Course': '狗隻敏捷入門班'}


def parse_courses(html, today: date | None = None):
    today = today or date.today()
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    for table in soup.find_all('table'):
        header = table.get_text(' ', strip=True)
        if 'Course Code' not in header or 'Enrol' not in header:
            continue
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 7:
                continue
            values = [c.get_text(' ', strip=True) for c in cells]
            if not re.fullmatch(r'[A-Z]\d{4,}', values[0]):
                continue
            # Do not invent individual sessions from ranges like “every Saturday”.
            dates = values[2]
            year_matches = re.findall(r'\b20\d{2}\b', table.get_text(' ', strip=True))
            context_years = re.findall(r'20\d{2}', ' '.join(a.get_text(' ',strip=True) for a in table.find_all_previous('a', limit=8) if re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', a.get_text())))
            year = int(year_matches[0]) if year_matches else int(context_years[0]) if context_years else None
            start = None
            match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})', dates)
            if match and year:
                start = datetime.strptime(f'{match[1]} {match[2]} {year}', '%b %d %Y').date().isoformat()
            end = None
            matches = list(re.finditer(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})', dates))
            if matches and year:
                last = matches[-1]
                end = datetime.strptime(f'{last[1]} {last[2]} {year}', '%b %d %Y').date().isoformat()
                if start and end < start:
                    end = None  # Cross-year ranges need an explicit year, not a guess.
            venue = values[5]
            result.append(Activity(id='spca:'+values[0], name=COURSE_LABELS.get(values[1], values[1]), name_en=values[1],
                category='訓練課程', dates_text=dates, start_date=start, end_date=end, venue_name=venue,
                place_id='curated:spca-tsing-yi' if 'Tsing Yi' in venue else 'curated:spca-wan-chai' if 'Hong Kong Centre' in venue else None,
                district='葵青' if 'Tsing Yi' in venue else '灣仔' if 'Hong Kong Centre' in venue else None,
                language_en=values[3], fee_text_en=values[4], venue_name_en=venue,
                description_en=f'SPCA {values[1]}. See the organiser’s page for full course details and entry requirements.',
                eligibility_en='Vaccination records, age and size requirements depend on the individual course. Check with the organiser.',
                language={'English':'英語','Chinese and English':'中文及英語','Chinese':'中文'}.get(values[3],values[3]), fee_text=values[4].replace('Non-Member:','非會員：').replace('Member:','會員：'), description=f'SPCA {COURSE_LABELS.get(values[1], values[1])}。完整課程內容同入學條件請睇主辦方頁面。',
                eligibility='疫苗紀錄、年齡同體型要求，以主辦方個別課程為準。',
                source_url=SPCA_URL, booking_url=safe_url(cells[6].find('a').get('href'), SPCA_URL) if cells[6].find('a') else None,
                source_name='香港愛護動物協會 SPCA'))
    if not result:
        raise ValueError('SPCA 課程表格式有變或暫時未有課程，保留舊快照並標示過期')
    return result
