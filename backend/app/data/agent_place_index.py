"""All saved venues, indexed once per published snapshot for Agent queries."""
import copy
from collections import defaultdict

from backend.app.data.geography import district_matches

AGENT_EXCLUDE = {'photos': True, 'restaurant_details': {
    'reviews', 'photo_authors', 'photo_url', 'photo_source_url', 'photo_credit',
    'dish_photo_url', 'dish_photo_source_url', 'dish_photo_credit', 'dish_photo_kind'}}


class AgentPlaceIndex:
    def __init__(self, places):
        self.rows = []
        self.categories = defaultdict(set)
        self.cuisines = defaultdict(set)
        self.districts = defaultdict(set)
        for position, place in enumerate(places):
            row = place.model_dump(mode='json', exclude=AGENT_EXCLUDE)
            self.rows.append(row)
            self.categories[row['category']].add(position)
            for cuisine in row['cuisines'] or ['未分類']:
                self.cuisines[cuisine].add(position)
            self.districts[row.get('district') or ''].add(position)

    def select(self, *, mode='', categories=(), cuisines=(), district='', query=''):
        eligible = None

        def intersect(positions):
            nonlocal eligible
            eligible = set(positions) if eligible is None else eligible & positions

        if mode:
            restaurants = self.categories.get('restaurants', set())
            intersect(restaurants if mode == 'restaurants' else set(range(len(self.rows))) - restaurants)
        if categories:
            intersect(set().union(*(self.categories.get(c, set()) for c in categories)))
        if cuisines:
            intersect(set().union(*(self.cuisines.get(c, set()) for c in cuisines)))
        if district:
            intersect(set().union(*(positions for saved, positions in self.districts.items()
                                    if district_matches(saved, district))))
        positions = range(len(self.rows)) if eligible is None else sorted(eligible)
        rows = [self.rows[i] for i in positions]
        if query:
            needle = query.casefold()
            rows = [p for p in rows if needle in ' '.join(filter(None, [
                p['name'], p.get('name_en'), p.get('address'), p.get('address_en'),
                (p.get('restaurant_details') or {}).get('display_name')])).casefold()]
        # Callers filter/rank/mutate results; the published index must stay immutable.
        return copy.deepcopy(rows)
