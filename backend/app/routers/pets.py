from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.app.config.container import Container
from backend.app.config.dependencies import get_container
from backend.app.data.sources import CATEGORIES, CUISINES

router = APIRouter(tags=['pets'])

@router.get('/health')
async def health():
    return {'status':'ok','application':'hk-petfinder'}

@router.get('/catalog')
async def catalog(c: Container = Depends(get_container)):
    return c.pets.catalogue()

@router.get('/places')
async def places(mode: Literal['restaurants','facilities'] | None = None,
                 category: list[str] = Query(default=[]), cuisine: list[str] = Query(default=[]),
                 district: str = Query(default='', max_length=80), q: str = Query(default='', max_length=200),
                 c: Container = Depends(get_container)):
    if any(k not in CATEGORIES for k in category) or any(k not in CUISINES for k in cuisine):
        raise HTTPException(422, '分類唔正確，請用 /catalog 提供嘅篩選值。')
    return c.pets.places(mode=mode or '', categories=category, cuisines=cuisine, district=district, query=q)

@router.get('/places/{place_id:path}')
async def place_detail(place_id: str, c: Container = Depends(get_container)):
    result = c.pets.places()
    result['items'] = [p for p in result['items'] if p['id']==place_id]
    if not result['items']:
        raise HTTPException(404, '暫時搵唔到呢個場地。')
    return {**result, 'total':1}

@router.get('/activities')
async def activities(category: str='', q: str=Query(default='',max_length=200), district: str='', c: Container = Depends(get_container)):
    return c.pets.activities(category=category,query=q,district=district)


@router.get('/restaurant-photos/{google_place_id}')
async def restaurant_photo(google_place_id: str):
    from fastapi.responses import FileResponse
    from backend.app.data.restaurant_details import photo_path
    path=photo_path(google_place_id)
    if path is None:
        raise HTTPException(404, 'Photo not found')
    return FileResponse(path, headers={'Cache-Control':'private, max-age=86400', 'X-Content-Type-Options':'nosniff'})


@router.get('/facility-photos/{token}')
async def facility_photo(token: str):
    from fastapi.responses import FileResponse
    from backend.app.data.google_facility_photos import photo_path
    path=photo_path(token)
    if path is None:
        raise HTTPException(404, 'Photo not found')
    return FileResponse(path, headers={'Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'})


@router.get('/restaurant-dish-photos/{google_place_id}')
async def restaurant_dish_photo(google_place_id: str):
    from fastapi.responses import FileResponse
    from backend.app.data.restaurant_details import dish_photo_path
    path=dish_photo_path(google_place_id)
    if path is None:raise HTTPException(404, 'Photo not found')
    return FileResponse(path, headers={'Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'})
