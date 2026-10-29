"""Prepare saved local photos only: python -m scripts.build_photo_variants. No Google calls."""
import json
from pathlib import Path

from backend.app.services.photo_service import prepare_variants

ROOT = Path(__file__).resolve().parents[1]


def photo_paths(root=ROOT):
    paths = set()
    for folder in (root/'data/google-places/photos', root/'data/google-facility-photos/photos'):
        if folder.is_dir():
            paths.update(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.avif','.img'})
    from backend.app.data.restaurant_details import dish_photo_path
    base = root/'data/google-places'
    try:
        for pid in json.loads((base/'dish-photos/selected.json').read_text()).get('places', {}):
            path = dish_photo_path(pid, base)
            if path:
                paths.add(path)
    except (OSError, ValueError):
        pass
    return sorted(paths)


def build(root=ROOT):
    paths = photo_paths(root)
    return {'photos':len(paths), 'generated':sum(prepare_variants(p) for p in paths)}


if __name__ == '__main__':
    print(json.dumps(build()))
