import asyncio
import gzip
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from agent.data.data_access import PetDataAccess
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from backend.app.models.pet import RestaurantDetails, Snapshot
from backend.app.services.photo_service import photo_response
from main import app
from test_pet_data import service


def container_for(svc,cache,client):
    return Container(Settings(api_key='test',model='test',base_url='https://example.invalid',cors_origins=[]),cache,client,svc)


def test_map_summaries_omit_reviews_but_details_preserve_them_and_etags_invalidate(tmp_path):
    svc,cache,client=service(tmp_path)
    place=svc.snapshot.places[1]
    place.restaurant_details=RestaurantDetails(google_place_id='test-place',rating=4.7,
        reviews=[{'text':'long review '*2000}],photo_url='/api/v1/restaurant-photos/test-place',hours=['Sunday: 10–20'])
    app.state.container=container_for(svc,cache,client)
    try:
        with TestClient(app) as api:
            summary=api.get('/api/v1/place-summaries');data=summary.json()
            row=next(p for p in data['items'] if p['id']==place.id)
            assert row['restaurant_details']['rating']==4.7
            assert 'reviews' not in row['restaurant_details'] and 'hours' not in row['restaurant_details']
            assert row['detail_loaded'] is False
            detail=api.get('/api/v1/places/'+place.id)
            assert detail.json()['items'][0]['restaurant_details']['reviews'][0]['text'].startswith('long review')
            assert len(detail.content)>len(summary.content)
            assert detail.headers['cache-control']=='private, no-store'
            not_modified=api.get('/api/v1/place-summaries',headers={'If-None-Match':summary.headers['etag']})
            assert not_modified.status_code==304 and not not_modified.content
            old_version=api.get('/api/v1/data-version').json()['revision']
            # Publishing a replacement snapshot invalidates both projected data and JSON bytes.
            updated=svc.snapshot.model_copy(deep=True);updated.places[1].restaurant_details.rating=4.1
            svc.snapshot=updated
            new=api.get('/api/v1/place-summaries',headers={'If-None-Match':summary.headers['etag']})
            assert new.status_code==200 and new.headers['etag']!=summary.headers['etag']
            assert api.get('/api/v1/data-version').json()['revision']!=old_version
            assert next(p for p in new.json()['items'] if p['id']==place.id)['restaurant_details']['rating']==4.1
    finally:del app.state.container


def test_cache_policies_do_not_share_auth_or_chat_and_catalog_supports_304(tmp_path):
    svc,cache,client=service(tmp_path);app.state.container=container_for(svc,cache,client)
    try:
        with TestClient(app) as api:
            r=api.get('/api/v1/catalog');assert 's-maxage=300' in r.headers['cache-control']
            assert api.get('/api/v1/catalog',headers={'If-None-Match':r.headers['etag']}).status_code==304
            assert 'no-store' in api.get('/api/v1/catalog',headers={'Authorization':'Bearer test'}).headers['cache-control']
            assert 's-maxage=60' in api.get('/api/v1/activities').headers['cache-control']
            assert 'no-store' in api.get('/api/v1/places/missing').headers['cache-control']
            assert 'private' in api.get('/api/v1/place-summaries').headers['cache-control']
    finally:del app.state.container


def test_thumbnails_are_smaller_keep_original_and_source_changes_invalidate(tmp_path):
    path=tmp_path/'photo.jpg'
    # A detailed large photo gives meaningful compression/resize savings.
    import random
    rng=random.Random(7)
    image=Image.frombytes('RGB',(1600,1200),rng.randbytes(1600*1200*3))
    image.save(path,quality=92)
    original=path.read_bytes()
    thumb=photo_response(path,'thumb');detail=photo_response(path,'detail')
    assert thumb.media_type=='image/webp' and len(thumb.body)<len(detail.body)<len(original)
    with Image.open(BytesIO(thumb.body)) as im:assert max(im.size)<=240
    with Image.open(BytesIO(detail.body)) as im:assert max(im.size)<=768
    assert path.read_bytes()==original
    assert photo_response(path,'thumb',thumb.headers['etag']).status_code==304
    assert thumb.headers['cache-control'].startswith('private')
    Image.new('RGB',(100,100),'blue').save(path)
    assert photo_response(path,'thumb').headers['etag']!=thumb.headers['etag']


def test_agent_reuses_identical_reads_and_omits_irrelevant_review_media(tmp_path,monkeypatch):
    async def run():
        svc,cache,client=service(tmp_path)
        place=svc.snapshot.places[1]
        place.restaurant_details=RestaurantDetails(google_place_id='test-place',rating=4.5,price_range={'endPrice':{'units':'150'}},
            reviews=[{'text':'review '*5000}],photo_authors=[{'displayName':'long photo metadata'}])
        calls=0;original=svc.places
        def counted(**kwargs):
            nonlocal calls
            calls+=1;return original(**kwargs)
        monkeypatch.setattr(svc,'places',counted)
        access=PetDataAccess(svc)
        try:
            a,b=await asyncio.gather(access.search_places(mode='restaurants'),access.search_places(mode='restaurants'))
            assert calls==1 and a==b
            assert 'reviews' not in a['items'][0]['restaurant_details']
            assert 'photo_authors' not in a['items'][0]['restaurant_details']
            assert a['items'][0]['restaurant_details']['price_range']['endPrice']['units']=='150'
            a['items'].clear()
            assert (await access.search_places(mode='restaurants'))['items'] # cached value cannot be mutated by caller
            details=await access.place_details(place.id,include_reviews=True)
            assert len(details['place']['restaurant_details']['reviews'][0]['text'])<=500
            assert access.recent_places([{'role':'assistant','content':place.name}])[0]['id']==place.id
        finally:await client.aclose();await cache.aclose()
    asyncio.run(run())


def test_replica_versions_are_content_based_not_checkout_timestamps(tmp_path):
    from backend.app.data.place_views import revision_of
    svc,cache,client=service(tmp_path)
    same=svc.snapshot.model_copy(deep=True)
    assert revision_of(svc.snapshot)==revision_of(same)
    same.places[0].notes.append('New published rule')
    assert revision_of(svc.snapshot)!=revision_of(same)
