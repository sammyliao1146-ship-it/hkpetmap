from agent.data.featured_answer import is_simple_nearby, render_nearby
from backend.app.data.featured import FeaturedStore, select_featured


def place(i, district, cuisine, rating, high, count=50, lat=22.3, lon=114.17):
    return {'id': f'r{i}', 'category': 'restaurants', 'name': f'n{i}', 'name_en': f'e{i}', 'district': district,
            'cuisines': [cuisine], 'latitude': lat + i * 0.001, 'longitude': lon, 'address': 'a',
            'restaurant_details': {'rating': rating, 'rating_count': count, 'price_range': {'endPrice': {'units': str(high)}}}}


def test_selection_filters_and_spreads_cuisines_and_districts():
    items = [place(i, 'A', '日式', 4.8, 100) for i in range(5)] + [place(10, 'A', '韓式', 4.5, 120), place(11, 'B', '西式', 4.4, 90),
             place(12, 'B', '西式', 3.5, 50), place(13, 'B', '中式', 4.9, None), place(14, 'B', '中式', 4.9, 80, count=2)]
    ids = [r['id'] for r in select_featured(items)]
    assert 'r12' not in ids and 'r13' not in ids and 'r14' not in ids
    first_three = ids[:3]
    assert 'r10' in first_three or 'r11' in first_three
    assert len({r['district'] for r in select_featured(items)}) == 2


def test_store_nearest_and_rebuild_once(tmp_path):
    store = FeaturedStore(tmp_path / 'f.db')
    items = [place(i, 'A', '日式', 4.6, 100) for i in range(6)]
    store.ensure(items, 'v1')
    assert store.nearest(22.3, 114.17, 3)[0]['id'] == 'r0'
    other = FeaturedStore(tmp_path / 'f.db')
    other.ensure([], 'v1')
    assert len(other.all()) == 6


def test_simple_nearby_detection():
    assert is_simple_nearby('附近有咩餐廳') and is_simple_nearby('find a restaurant nearby')
    assert not is_simple_nearby('附近日式餐廳') and not is_simple_nearby('i want sushi nearby') and not is_simple_nearby('附近公園')
