import asyncio
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from backend.app.config.container import Container
from backend.app.config.dependencies import get_container
from backend.app.services.http_views import versioned_json
from backend.app.data.sources import CATEGORIES, CUISINES

router = APIRouter(tags=['pets'])

@router.get('/health')
async def health():
    return {'status':'ok','application':'hk-petfinder'}

@router.get('/catalog')
async def catalog(request: Request, c: Container = Depends(get_container)):
    return versioned_json(request,c.pets,'catalog',c.pets.catalogue,'public, max-age=0, s-maxage=300')

@router.get('/data-version')
async def data_version(request: Request, c: Container=Depends(get_container)):
    return versioned_json(request,c.pets,'version',lambda:{'revision':c.pets.data_revision()},'public, max-age=0, s-maxage=30')


@router.get('/place-summaries')
async def place_summaries(request: Request, c: Container=Depends(get_container)):
    return versioned_json(request,c.pets,'summaries',c.pets.summaries)


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
    item=c.pets.place(place_id)
    if item is None:
        raise HTTPException(404,'暫時搵唔到呢個場地。')
    return {'status':c.pets._status(),'fetched_at':c.pets.snapshot.fetched_at.isoformat(),
            'items':[{**item,'detail_loaded':True}],'total':1,'sources':[]}

@router.get('/activities')
async def activities(category: str='', q: str=Query(default='',max_length=200), district: str='', c: Container = Depends(get_container)):
    return c.pets.activities(category=category,query=q,district=district)


@router.get('/restaurant-photos/{google_place_id}')
async def restaurant_photo(google_place_id: str, request: Request, size: Literal['thumb','detail','original']='detail'):
    from backend.app.data.restaurant_details import photo_path
    path=photo_path(google_place_id)
    if path is None:
        raise HTTPException(404, 'Photo not found')
    from backend.app.services.photo_service import photo_response
    return await asyncio.to_thread(photo_response,path,size,request.headers.get('if-none-match'))


@router.get('/facility-photos/{token}')
async def facility_photo(token: str, request: Request, size: Literal['thumb','detail','original']='detail'):
    from backend.app.data.google_facility_photos import photo_path
    path=photo_path(token)
    if path is None:
        raise HTTPException(404, 'Photo not found')
    from backend.app.services.photo_service import photo_response
    return await asyncio.to_thread(photo_response,path,size,request.headers.get('if-none-match'))


@router.get('/restaurant-dish-photos/{google_place_id}')
async def restaurant_dish_photo(google_place_id: str, request: Request, size: Literal['thumb','detail','original']='detail'):
    from backend.app.data.restaurant_details import dish_photo_path
    path=dish_photo_path(google_place_id)
    if path is None:raise HTTPException(404, 'Photo not found')
    from backend.app.services.photo_service import photo_response
    return await asyncio.to_thread(photo_response,path,size,request.headers.get('if-none-match'))
