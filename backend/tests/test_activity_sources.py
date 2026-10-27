import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend.app.cache.redis_cache import RedisCache
from backend.app.data.activity_sources import CARE_URL, SOURCES, article_links, date_ranges, parse_afcd, parse_care, parse_wnp
from backend.app.models.pet import Activity, Place, Snapshot
from backend.app.services.pet_service import PetService

TODAY = date(2026, 10, 23)
CARE = '''<table><thead><tr><th>Date</th><th>Fee $ (Member)</th><th>Enroll Link</th></tr></thead><tbody>
<tr><td>17 Oct 2026 (Sat)</td><td>Feline First Aid</td><td>Cantonese</td><td>10:00-17:00</td><td>1300</td><td>1600</td><td>Tsing Yi Centre</td><td>FULL</td></tr>
<tr><td>7 Nov 2026 (Sat)</td><td>Canine First Aid</td><td>Cantonese</td><td>10:00-17:00</td><td>1200</td><td>1500</td><td>Tsing Yi Centre</td><td>FULL</td></tr>
<tr><td>12 Dec 2026 (Sat)</td><td>Basic Pet Nutrition</td><td>English</td><td>13:00-15:00</td><td>450</td><td>550</td><td>Tsing Yi Centre</td><td><a href="https://eduenrol.spca.org.hk/register">Enroll</a></td></tr>
</tbody></table>'''


def test_care_dates_fees_full_status_and_unknown_remaining():
    rows = parse_care(CARE, TODAY)
    assert len(rows) == 2
    assert rows[0].start_date == '2026-11-07'
    assert rows[0].registration_status == 'full'
    assert rows[0].remaining is None and rows[0].booking_url is None
    assert rows[1].registration_status == 'open'
    assert rows[1].place_id == 'curated:spca-tsing-yi'
    assert 'HK$550' in rows[1].fee_text
    assert len({a.id for a in rows}) == 2


def test_layout_change_is_error_but_valid_expired_table_is_empty():
    with pytest.raises(ValueError): parse_care('<html>blocked</html>', TODAY)
    assert parse_care(CARE, date(2027, 1, 1)) == []
    with pytest.raises(ValueError): parse_care(CARE.replace('7 Nov 2026', 'date unknown'), TODAY)


def test_afcd_only_live_event_and_no_invented_booking_or_coordinates():
    html = '''<div id="mainContent"><h3>寵物巡迴展覽</h3>費用全免。
    日期：2026年10月9日 時間︰上午11時至下午6時 地點：尖沙咀 主題：寵物
    日期：2026年10月23日 時間︰上午11時至下午6時 地點：啟德車站廣場 主題：寵物</div>'''
    rows = parse_afcd(html, 'https://www.pets.gov.hk/event.html', TODAY)
    assert len(rows) == 1 and rows[0].venue_name == '啟德車站廣場'
    assert rows[0].fee_text == '免費'
    assert rows[0].place_id is None and rows[0].booking_url is None
    assert parse_afcd(html.replace('寵物巡迴展覽', '活動取消'), 'https://www.pets.gov.hk/event.html', TODAY) == []


def wnp(content):
    return '<h1>寵物派對</h1><time>2026-10-23</time><div itemprop="articleBody">'+content+'</div>'


def test_wnp_article_publication_is_not_event_date():
    assert parse_wnp(wnp('歡迎參加！日期稍後公布'), 'https://zh.wnp.com.hk/blogs/events/test', TODAY) == []
    assert parse_wnp(wnp('日期：10月24日'), 'https://zh.wnp.com.hk/blogs/events/test', TODAY) == []


def test_wnp_distinct_branches_and_range():
    url = 'https://zh.wnp.com.hk/blogs/events/test'
    rows = parse_wnp(wnp('鴨脷洲店：2026年10月24日（星期六）| The LOHAS 康城店：2026年10月25日（星期日） 活動時間：下午2時至6時'), url, TODAY)
    assert len(rows) == 2
    assert [r.start_date for r in rows] == ['2026-10-24', '2026-10-25']
    assert rows[0].venue_name == '鴨脷洲店' and rows[1].venue_name == 'The LOHAS 康城店'
    assert rows[0].registration_status == 'unknown' and rows[0].remaining is None
    rows = parse_wnp(wnp('活動地點：Elements 推廣日期及時間：2026年9月30日（星期三）– 10月31日（星期六）'), url, TODAY)
    assert rows[0].start_date == '2026-09-30' and rows[0].end_date == '2026-10-31'
    assert rows[0].venue_name == 'Elements'


def test_link_discovery_excludes_sales_external_hosts_and_recaps():
    html = '''<a href="/blogs/events/sale">11.11 限時激賞</a>
    <a href="/blogs/events/party">寵物派對</a><a href="/blogs/events/party">寵物派對</a>
    <a href="https://evil.example/blogs/events/party">寵物派對</a>'''
    assert article_links(html, 'https://zh.wnp.com.hk/blogs/events', 'wnp', TODAY) == ['https://zh.wnp.com.hk/blogs/events/party']
    assert date_ranges('2026年12月31日至2027年1月1日')[0][1] == date(2027, 1, 1)
    with pytest.raises(ValueError): date_ranges('2026年12月31日至1月1日')


def test_source_failure_preserves_only_its_own_old_activities_and_timestamp(tmp_path):
    async def run():
        now = datetime.now(ZoneInfo('Asia/Hong_Kong'))
        cache = RedisCache(None, 'activity-test')
        def respond(request):
            if str(request.url) == CARE_URL:
                return httpx.Response(200, text=CARE.replace('2026', str(now.year + 1)))
            return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            svc = PetService(cache, client, tmp_path/'snapshot.json')
            def a(id):
                return Activity(id=id, name=id, dates_text='日期待確認', description='test', source_url=CARE_URL, source_name='test')
            svc.snapshot = Snapshot(fetched_at=now, places=[Place(id='restaurant:1', name='餐廳', category='restaurants', source_url=CARE_URL, source_name='test')],
                activities=[a('spca:A1'), a('spca-care:old'), a('afcd-event:old'), a('wnp-event:old')],
                sources=[{'key': key, 'fetched_at': '2026-01-01T00:00:00+08:00'} for key in ['restaurants', 'activities', *SOURCES]])
            await svc.refresh(force=True, activities_only=True)
            ids = [a.id for a in svc.snapshot.activities]
            assert len(ids) == len(set(ids))
            assert {'spca:A1', 'afcd-event:old', 'wnp-event:old'} <= set(ids)
            assert 'spca-care:old' not in ids
            assert [p.id for p in svc.snapshot.places] == ['restaurant:1']
            statuses = {s['key']: s for s in svc.snapshot.sources}
            assert statuses['activities_wnp']['status'] == 'stale'
            assert statuses['activities_wnp']['fetched_at'] == '2026-01-01T00:00:00+08:00'
            assert statuses['activities_care']['status'] == 'ready'
            assert statuses['restaurants']['fetched_at'] == '2026-01-01T00:00:00+08:00'
            assert svc.snapshot.fetched_at == now
        await cache.aclose()
    asyncio.run(run())


def test_wnp_old_article_index_is_skipped_without_inventing_event_date():
    html = '<div class="article-card__info"><a href="/blogs/events/old">寵物派對</a>31 August 2025</div><a href="/blogs/events/new">寵物派對</a>'
    assert article_links(html, 'https://zh.wnp.com.hk/blogs/events', 'wnp', TODAY) == ['https://zh.wnp.com.hk/blogs/events/new']
