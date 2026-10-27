from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.config.container import Container
from backend.app.config.dependencies import get_container

router = APIRouter(tags=['parking'])


@router.get('/parking')
async def parking(latitude: float | None = Query(default=None, ge=-90, le=90),
                  longitude: float | None = Query(default=None, ge=-180, le=180),
                  radius_m: float = Query(default=1000, gt=0, le=50000),
                  limit: int = Query(default=1000, ge=1, le=1000),
                  language: Literal['en','zh-Hant'] = 'en',
                  c: Container = Depends(get_container)):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, 'Supply both latitude and longitude.')
    if latitude is not None:
        return await c.parking.nearby(latitude,longitude,radius_m,limit,language)
    data = await c.parking.list(language)
    return {**data,'items':data['items'][:limit]}
