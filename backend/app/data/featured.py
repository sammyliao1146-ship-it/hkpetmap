"""Curated shortlist of restaurants (high rating, low price, varied cuisine and district) in its own SQLite DB."""
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from agent.data.place_search import distance_m, price_ceiling

DB_PATH = Path(__file__).resolve().parents[3] / 'data' / 'featured.db'
MAX_ITEMS = 150
MAX_PER_DISTRICT = 12
MIN_RATING = 4.0
MIN_RATING_COUNT = 10
PRICE_CAP = 400.0
PRIOR_RATING, PRIOR_WEIGHT = 4.0, 20
CUISINE_REPEAT_PENALTY = 0.08

SCHEMA = '''CREATE TABLE IF NOT EXISTS featured_restaurants(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, name_en TEXT, district TEXT, cuisine TEXT NOT NULL,
  rating REAL NOT NULL, rating_count INTEGER NOT NULL, price_min REAL, price_max REAL NOT NULL,
  latitude REAL NOT NULL, longitude REAL NOT NULL, address TEXT, address_en TEXT, score REAL NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);'''


def _price_min(profile):
    try:
        return float(((profile.get('price_range') or {}).get('startPrice') or {}).get('units'))
    except (TypeError, ValueError):
        return None


def _candidates(items):
    for p in items:
        d = p.get('restaurant_details') or {}
        rating, count = d.get('rating'), d.get('rating_count') or 0
        ceiling = price_ceiling(d)
        lat, lon = p.get('latitude'), p.get('longitude')
        if p.get('category') != 'restaurants' or lat is None or lon is None or ceiling is None:
            continue
        if not isinstance(rating, (int, float)) or not math.isfinite(rating) or rating < MIN_RATING or count < MIN_RATING_COUNT:
            continue
        quality = (rating * count + PRIOR_RATING * PRIOR_WEIGHT) / (count + PRIOR_WEIGHT)
        score = 0.65 * quality / 5 + 0.35 * (1 - min(ceiling, PRICE_CAP) / PRICE_CAP)
        yield {'id': p['id'], 'name': d.get('display_name') or p['name'], 'name_en': p.get('name_en'),
               'district': p.get('district') or '', 'cuisine': (p.get('cuisines') or ['未分類'])[0],
               'rating': float(rating), 'rating_count': int(count), 'price_min': _price_min(d), 'price_max': ceiling,
               'latitude': float(lat), 'longitude': float(lon), 'address': p.get('address'),
               'address_en': p.get('address_en'), 'score': score}


def select_featured(items, limit=MAX_ITEMS):
    """Round-robin over districts; inside a district prefer high score and cuisines not yet chosen."""
    by_district = defaultdict(list)
    for c in _candidates(items):
        by_district[c['district']].append(c)
    for rows in by_district.values():
        rows.sort(key=lambda r: (-r['score'], r['id']))
    cuisines, chosen = Counter(), []
    districts = sorted(by_district, key=lambda d: (-len(by_district[d]), d))
    while len(chosen) < limit and any(by_district.values()):
        progressed = False
        for district in districts:
            rows = by_district[district]
            taken = sum(r['district'] == district for r in chosen)
            if not rows or taken >= MAX_PER_DISTRICT or len(chosen) >= limit:
                continue
            best = max(rows, key=lambda r: (r['score'] - CUISINE_REPEAT_PENALTY * cuisines[r['cuisine']], r['id']))
            rows.remove(best)
            chosen.append(best)
            cuisines[best['cuisine']] += 1
            progressed = True
        if not progressed:
            break
    return chosen


class FeaturedStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = Path(path)
        self.version = ''

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        return conn

    def rebuild(self, items, version: str) -> int:
        rows = select_featured(items)
        with self._connect() as conn:
            conn.execute('DELETE FROM featured_restaurants')
            conn.executemany(
                'INSERT INTO featured_restaurants VALUES(:id,:name,:name_en,:district,:cuisine,:rating,:rating_count,'
                ':price_min,:price_max,:latitude,:longitude,:address,:address_en,:score)', rows)
            conn.execute("INSERT OR REPLACE INTO meta VALUES('version',?)", (version,))
        conn.close()
        self.version = version
        return len(rows)

    def ensure(self, items, version: str) -> None:
        """Rebuild only when the underlying snapshot changed."""
        if self.version == version:
            return
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        conn.close()
        if row and row['value'] == version:
            self.version = version
        else:
            self.rebuild(items, version)

    def all(self) -> list[dict]:
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute('SELECT * FROM featured_restaurants')]
        conn.close()
        return rows

    def nearest(self, latitude: float, longitude: float, limit: int = 5) -> list[dict]:
        origin = (latitude, longitude)
        rows = self.all()
        for r in rows:
            r['distance_m'] = round(distance_m(origin, r['latitude'], r['longitude']), 1)
        return sorted(rows, key=lambda r: (r['distance_m'], r['id']))[:limit]
