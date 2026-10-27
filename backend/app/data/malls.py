"""Curated mall import with explicit policy provenance; no invented access guarantees."""
import json
from pathlib import Path
from backend.app.models.pet import Place

MANIFEST = Path(__file__).with_name('malls.json')
MALL_SOURCE = 'https://www.petchillhk.com/blog/articles/petguide-hk-pet-friendly-malls/'


def load_malls(path=MANIFEST):
    data = json.loads(path.read_text())
    items = [Place.model_validate(row) for row in data['records']]
    if not items or len({p.id for p in items}) != len(items):
        raise ValueError('Empty or duplicate mall records')
    if any(p.category != 'malls' or p.mall_policy is None for p in items):
        raise ValueError('Mall records require category and provenance')
    return items


def merge_malls(places, malls=None):
    """Update stable IDs on cached loads as well as regular source refreshes."""
    malls = load_malls() if malls is None else malls
    replacements = {p.id: p for p in malls}
    result = []
    for prior in places:
        replacement = replacements.pop(prior.id, None)
        if replacement:
            replacement = replacement.model_copy(deep=True)
            if not replacement.photos:
                replacement.photos = prior.photos
            result.append(replacement)
        else:
            result.append(prior)
    result.extend(replacements.values())
    return result


def mall_source_status(items):
    return {'key':'malls','label':'寵物友善商場','url':MALL_SOURCE,'status':'ready',
            'count':len(items),'skipped':0,'fetched_at':json.loads(MANIFEST.read_text())['imported_at'],
            'message':'目錄日期 2026-09-17；逐場顯示官方核對或第三方資料狀態。'}
