"""Bounded readers of public activity pages, not private enrolment APIs."""
import asyncio
import re

import httpx
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from backend.app.data.adapters import identity, safe_url
from backend.app.models.pet import Activity

CARE_URL = 'https://www.spca.org.hk/animal-care-services/pet-care-courses/pet-care-courses/'
AFCD_URL = 'https://www.pets.gov.hk/tc_chi/highlights/highlights.html'
WNP_URL = 'https://zh.wnp.com.hk/blogs/events'
SOURCES = {
    'activities_care': {'name': 'SPCA 寵物護理課程', 'name_en': 'SPCA Pet Care+ courses', 'url': CARE_URL, 'integration': 'public_web_table', 'prefix': 'spca-care:'},
    'activities_afcd': {'name': '漁護署寵物活動', 'name_en': 'AFCD pet events', 'url': AFCD_URL, 'integration': 'public_event_pages', 'prefix': 'afcd-event:'},
    'activities_wnp': {'name': 'WNP 寵物活動', 'name_en': 'WNP pet events', 'url': WNP_URL, 'integration': 'public_event_pages', 'prefix': 'wnp-event:'},
}


def hk_today():
    return datetime.now(ZoneInfo('Asia/Hong_Kong')).date()


def parse_care(html, today=None):
    today = today or hk_today()
    soup = BeautifulSoup(html, 'html.parser')
    tables = [t for t in soup.select('table') if 'Fee $ (Member)' in t.get_text(' ', strip=True) and 'Enroll Link' in t.get_text(' ', strip=True)]
    if not tables:
        raise ValueError('SPCA Pet Care+ table missing')
    result = []
    labels = {'Feline First Aid': '貓隻急救課程', 'Canine First Aid': '狗隻急救課程', 'Geriatric Dog Care': '老年犬護理', 'Basic Pet Nutrition': '寵物基礎營養', 'Dog Care for Owners': '狗主護理課程'}
    for table in tables:
        for row in table.select('tbody tr'):
            cells = row.find_all('td')
            if not cells:
                continue
            if len(cells) != 8:
                raise ValueError('Unexpected Pet Care+ row')
            values = [c.get_text(' ', strip=True) for c in cells]
            match = re.search(r'\d{1,2}\s+[A-Za-z]{3}\s+20\d{2}', values[0])
            if not match:
                raise ValueError('Pet Care+ date missing')
            day = datetime.strptime(match[0], '%d %b %Y').date()
            if day < today:
                continue
            link = cells[7].find('a', href=True)
            full = bool(re.search(r'\bFULL\b|已滿|額滿', values[7], re.I))
            venue = values[6]
            result.append(Activity(
                id='spca-care:' + identity('|'.join([values[0], values[1], values[3], venue])),
                name=labels.get(values[1], values[1]), name_en=values[1], category='護理課程',
                dates_text=f'{values[0]} · {values[3]}', start_date=day.isoformat(), end_date=day.isoformat(),
                venue_name=venue, venue_name_en=venue,
                place_id='curated:spca-tsing-yi' if venue == 'Tsing Yi Centre' else 'curated:spca-wan-chai' if venue == 'Hong Kong Centre' else None,
                district='葵青' if venue == 'Tsing Yi Centre' else '灣仔' if venue == 'Hong Kong Centre' else None,
                language={'Cantonese': '廣東話', 'English': '英語'}.get(values[2], values[2]), language_en=values[2],
                fee_text=f'會員：HK${values[4]}；非會員：HK${values[5]}',
                fee_text_en=f'Member: HK${values[4]}; Non-member: HK${values[5]}',
                registration_status='full' if full else 'open' if link else 'unknown',
                description='SPCA 公開寵物護理課程；內容及參加條件請參閱主辦方。',
                description_en='SPCA public pet-care course. See the organiser for content and entry requirements.',
                source_url=CARE_URL, source_name='香港愛護動物協會 SPCA', source_name_en='SPCA (Hong Kong)',
                booking_url=safe_url(link['href'], CARE_URL) if link and not full else None,
            ))
    return result


# Require an explicit year in the activity text. Never use article publication dates.
CN_DATE = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
RANGE_END = re.compile(r'^\s*(?:[（(][^）)]*[）)])?\s*[–—\-至到]\s*(?:(20\d{2})\s*年\s*)?(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日')


def date_ranges(content):
    result, consumed = [], 0
    for match in CN_DATE.finditer(content):
        if match.start() < consumed:
            continue
        start = date(*map(int, match.groups()))
        end_match = RANGE_END.match(content[match.end():])
        end = start
        end_pos = match.end()
        if end_match:
            end = date(int(end_match[1] or start.year), int(end_match[2] or start.month), int(end_match[3]))
            end_pos += end_match.end()
            if end < start:
                raise ValueError('Ambiguous cross-year activity range')
        consumed = end_pos
        result.append((start, end, content[match.start():end_pos], match.start(), end_pos))
    return result


def labelled(content, labels):
    match = re.search(r'(?:' + labels + r')\s*[：:︰]\s*(.+?)(?=\s+(?:日期|時間|地點|主題|費用|活動時間|活動地點|推廣日期及時間|限定優惠|消費禮遇)\s*[：:︰]|$)', content)
    return match[1].strip()[:250] if match else None


def parse_afcd(html, url, today=None):
    today = today or hk_today()
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('#mainContent')
    if body is None:
        raise ValueError('AFCD activity content missing')
    content = body.get_text(' ', strip=True)
    heading = body.select_one('h3, h1')
    title = heading.get_text(' ', strip=True) if heading else '漁護署寵物活動'
    # Recaps and cancellation announcements are never upcoming activities.
    if re.search(r'花絮|回顧|活動現需取消|活動取消|活動將會取消', title + ' ' + content[:500]):
        return []
    blocks = re.split(r'日期\s*[：:︰]', content)[1:]
    result = []
    for block in blocks:
        ranges = date_ranges(block)
        if not ranges:
            continue
        start, end, raw, _, _ = ranges[0]
        if end < today:
            continue
        venue = labelled(block, '地點')
        result.append(Activity(id='afcd-event:' + identity(f'{url}|{raw}|{venue}'), name=title,
            category='展覽／領養活動', dates_text=raw + (' · ' + labelled(block, '時間') if labelled(block, '時間') else ''),
            start_date=start.isoformat(), end_date=end.isoformat(), venue_name=venue,
            fee_text='免費' if '費用全免' in content else None,
            description='漁護署公開寵物教育／領養活動；活動安排、攜寵條件及天氣變更請參閱官方公告。',
            description_en='AFCD public pet event. Check the official notice for arrangements, pet access and weather changes.',
            source_url=url, source_name='漁護署寵物活動', source_name_en='AFCD pet events'))
    return result


def article_links(html, base, kind, today=None):
    today = today or hk_today()
    soup = BeautifulSoup(html, 'html.parser')
    result = []
    for a in soup.select('a[href]'):
        title = a.get_text(' ', strip=True)
        url = safe_url(a['href'], base)
        if not title or not url or urlparse(url).hostname != urlparse(base).hostname:
            continue
        if kind == 'wnp':
            card = a.find_parent(class_='article-card__info')
            published = re.search(r'\b(20\d{2})\b', card.get_text(' ', strip=True)) if card else None
            # Bound discovery to this year's posts; publication dates never become event dates.
            if published and int(published[1]) < today.year:
                continue
            if '/blogs/events/' not in urlparse(url).path or not re.search(r'派對|工作坊|講座|領養|嘉年華|慶典|慶祝|Pop.Up|Party|Workshop|Fest', title, re.I):
                continue
        else:
            if not re.search(r'展覽|領養|訓練課程|嘉年華', title) or re.search(r'花絮|回顧|通知|安排|結果|取消', title):
                continue
            years = re.findall(r'20\d{2}', title + ' ' + urlparse(url).path)
            if years and max(map(int, years)) < today.year:
                continue
            if not urlparse(url).path.endswith(('.html', '.htm')):
                continue
        if url not in result:
            result.append(url)
    if not result:
        raise ValueError('Activity index links missing or layout changed')
    return result[:20 if kind == 'wnp' else 8]


def parse_wnp(html, url, today=None):
    today = today or hk_today()
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('[itemprop="articleBody"]')
    heading = soup.select_one('h1')
    if body is None or heading is None:
        raise ValueError('WNP article content missing')
    title = heading.get_text(' ', strip=True)
    content = body.get_text(' ', strip=True)
    if re.search(r'活動取消|已取消', content):
        return []
    # Only paragraphs with explicit years are converted to dated events.
    ranges = date_ranges(content)
    result = []
    for start, end, raw, offset, end_pos in ranges:
        if end < today:
            continue
        venue = labelled(content, '活動地點|地點')
        # Some articles contain distinct dates for different branches.
        branch = re.search(r'([^。！？|：:]{2,35}(?:店|場))\s*[：:]\s*$', content[max(0, offset-50):offset])
        if branch:
            venue = branch[1].strip()
        time_match = re.search(r'活動時間\s*[：:︰]\s*((?:上午|下午|晚上)?\s*\d{1,2}\s*時(?:\s*\d{1,2}\s*分)?\s*[至–—-]\s*(?:上午|下午|晚上)?\s*\d{1,2}\s*時(?:\s*\d{1,2}\s*分)?)', content)
        time = time_match[1] if time_match else None
        # Explicit event block with daily hours, without guessing opening hours.
        if not time:
            daily = re.search(r'每日\s+[^。]{1,40}?(?:PM|AM|時|分)(?=\s+(?:限定|消費)|$)', content, re.I)
            time = daily[0] if daily else None
        booking = next((safe_url(a['href'], url) for a in body.select('a[href]') if re.search(r'報名|預約|RSVP|Register|Book now', a.get_text(' ', strip=True), re.I) and safe_url(a['href'], url)), None)
        result.append(Activity(id='wnp-event:' + identity(f'{url}|{raw}|{venue}'), name=title,
            category='工作坊' if re.search(r'工作坊|講座|Workshop', title, re.I) else '寵物派對／市集',
            dates_text=raw + (' · ' + time if time else ''), start_date=start.isoformat(), end_date=end.isoformat(),
            venue_name=venue, description='WNP 公開寵物活動；詳細安排、費用、報名及攜寵條件請參閱主辦方原文。',
            description_en='WNP public pet event. See the organiser for details, fees, enrolment and pet-access rules.',
            source_url=url, source_name='Whiskers N Paws', source_name_en='Whiskers N Paws', booking_url=booking))
    return list({a.id: a for a in result}.values())


async def fetch_source(get, key, today=None):
    today = today or hk_today()
    meta = SOURCES[key]
    async def request(url):
        for attempt in range(3):
            try:
                return await get(url)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (429, 500, 502, 503, 504):
                    raise
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
    response = await request(meta['url'])
    if key == 'activities_care':
        return parse_care(response.text, today), 0
    kind = 'wnp' if key == 'activities_wnp' else 'afcd'
    links = article_links(response.text, meta['url'], kind, today)
    semaphore = asyncio.Semaphore(2)
    async def read(url):
        async with semaphore:
            r = await request(url)
            return (parse_wnp if kind == 'wnp' else parse_afcd)(r.text, url, today)
    # A detail failure fails this source, preserving its previous snapshot.
    pages = await asyncio.gather(*(read(url) for url in links))
    items = list({a.id: a for page in pages for a in page}.values())
    return items, sum(not page for page in pages)
