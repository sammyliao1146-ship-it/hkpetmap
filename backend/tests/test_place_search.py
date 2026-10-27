import asyncio
import math
import pytest
from agents import function_tool
from agent.data.place_search import select_places
from agent.data.data_access import PetDataAccess
from agent.data.tools.pet_data import make_pet_queries
from backend.app.models.pet import Place,RestaurantDetails
from backend.app.models.assistant import ChatRequest
from test_pet_data import service

def item(i,**kwargs):
    return {'id':str(i),'latitude':22.3+i*.001,'longitude':114.17,'restaurant_details':{'rating':3+i*.1,'rating_count':i},**kwargs}
def data(items):return {'items':items,'total':len(items),'mapped':len(items),'status':'ready','sources':[]}

def test_rating_ranks_complete_set_and_ties_before_limit():
    rows=[item(i) for i in range(12)];rows[0]['restaurant_details']={'rating':4.1,'rating_count':100}
    rows.append(item(20,restaurant_details=None))
    result=select_places(data(rows),sort_by='rating',limit=2)
    assert [p['id'] for p in result['items']]==['0','11']
    assert result['total']==12 and result['filtered_total']==13 and result['missing_ratings']==1 and result['truncated']
    assert rows[0].get('distance_m') is None


def test_distance_and_radius_use_full_set_skip_missing_coordinates():
    rows=[item(i) for i in range(12)]+[item(20,latitude=None,longitude=None)]
    r=select_places(data(rows),sort_by='distance',origin=(22.311,114.17),limit=2)
    assert [p['id'] for p in r['items']]==['11','10'];assert r['items'][0]['distance_m']==pytest.approx(0,abs=.1)
    assert r['missing_coordinates']==1 and r['total']==12 and r['distance_type']=='straight_line'
    r=select_places(data(rows),sort_by='rating',origin=(22.311,114.17),radius_m=150,min_rating=4,limit=8)
    assert {p['id'] for p in r['items']}=={'10','11'}
    assert r['items'][0]['id']=='11'


def test_missing_origin_is_actionable_and_invalid_origin_never_guessed():
    r=select_places(data([item(0)]),sort_by='distance')
    assert r['query_status']=='needs_location' and r['items']==[] and r['filtered_total']==1
    for kwargs in [{'origin':(math.nan,114)},{'origin':(91,114)},{'radius_m':0},{'min_rating':6},{'sort_by':'invented'}]:
        with pytest.raises(ValueError):select_places(data([item(0)]),**kwargs)
    with pytest.raises(ValueError):ChatRequest(message='nearby',origin={'latitude':float('nan'),'longitude':114})


def test_random_samples_entire_eligible_set_without_duplicates(monkeypatch):
    captured=[]
    def sample(self,population,k):captured.append(len(population));return list(reversed(population))[:k]
    monkeypatch.setattr('agent.data.place_search.random.SystemRandom.sample',sample)
    r=select_places(data([item(i) for i in range(12)]),sort_by='random',limit=3)
    assert captured==[12] and [p['id'] for p in r['items']]==['11','10','9']
    assert len({p['id'] for p in r['items']})==3 and r['total']==12
    assert select_places(data([]),sort_by='random')['items']==[]


def test_tools_combine_cuisine_and_rating_and_resolve_explicit_map_origin(tmp_path):
    async def run():
        svc,cache,client=service(tmp_path)
        try:
            svc.snapshot.places=[Place(id=f'restaurant:{i}',category='restaurants',name=f'Cafe {i}',source_url='https://example.com',source_name='test',latitude=22.3+i*.001,longitude=114.17,cuisines=['日式'] if i%2 else ['中式'],cuisine_source='https://example.com/cuisine',restaurant_details=RestaurantDetails(google_place_id=f'place{i}',rating=3+i*.1,rating_count=i)) for i in range(12)]
            access=PetDataAccess(svc)
            r=await access.search_places(mode='restaurants',cuisine='日式',sort_by='rating',limit=2)
            assert [p['id'] for p in r['items']]==['restaurant:11','restaurant:9'];assert r['total']==6
            r=await access.search_places(cuisine='中式',sort_by='distance',origin_place_id='restaurant:11',limit=1)
            assert r['items'][0]['id']=='restaurant:10'
            assert (await access.search_places(sort_by='distance',origin_place_id='missing'))['query_status']=='needs_location'
            assert (await PetDataAccess(svc,origin=(22.311,114.17)).search_places(sort_by='distance',limit=1))['items'][0]['id']=='restaurant:11'
            with pytest.raises(ValueError):await access.search_places(sort_by='distance',latitude=22.3)
            tool=next(function_tool(q) for q in make_pet_queries(access) if q.__name__=='search_pet_places')
            assert {'sort_by','radius_m','min_rating','origin_place_id','latitude','longitude'}<=set(tool.params_json_schema['properties'])
        finally:await client.aclose();await cache.aclose()
    asyncio.run(run())


def test_filter_aliases_and_invalid_filter_are_recoverable():
    import asyncio
    from agent.data.data_access import PetDataAccess
    class P:
        def places(self,**k): return {'items':[{'id':'a','latitude':22.3,'longitude':114.17}],'status':'ok'}
    access=PetDataAccess(P(),origin=(22.3,114.17))
    ok=asyncio.run(access.search_places(mode='restaurant',cuisine='Japanese',sort_by='distance'))
    assert ok['query_status']=='ready' and ok['returned']==1
    bad=asyncio.run(access.search_places(cuisine='Martian'))
    assert bad['query_status']=='invalid_filter' and '日式' in bad['valid_cuisines']


def test_max_price_filters_by_price_ceiling_and_excludes_unpriced():
    def rest(i,end):
        pr={'endPrice':{'units':str(end)}} if end else None
        return {'id':str(i),'latitude':22.3,'longitude':114.17,'restaurant_details':{'rating':4,'price_range':pr}}
    out=select_places({'items':[rest(1,100),rest(2,300),rest(3,None)]},max_price=200)
    assert [p['id'] for p in out['items']]==['1'] and out['excluded_without_price']==1
