import asyncio
from types import SimpleNamespace

import pytest

from backend.app.models.plan import PlanRequest
from backend.app.services.outing_plan import build_candidates, create_plan, distance, group_by_parking, local_areas, prefer_single_parking


def place(id, category, lat=22.2828, lon=114.1666, **extra):
    return {'id':id,'category':category,'name':id,'name_en':id,'district':'中西區',
            'latitude':lat,'longitude':lon,'pet_policy':'dogs_permitted',
            'source_url':'https://www.lcsd.gov.hk/','notes':[],**extra}


def test_single_carpark_covering_all_modules_excludes_unnecessary_driving_moves():
    parks=[place('near','parking'),place('far','parking',lon=114.2)]
    candidates=[
        {'id':'park','purpose':'park','place':place('park','pet_parks'),'parking_ids':['near']},
        {'id':'mall','purpose':'mall','place':place('mall','malls'),'parking_ids':['near']},
        {'id':'near-meal','purpose':'meal','place':place('near-meal','restaurants'),'parking_ids':['near']},
        {'id':'far-meal','purpose':'meal','place':place('far-meal','restaurants',lon=114.2),'parking_ids':['far']},
    ]
    selected=prefer_single_parking(candidates,parks,parks[0])
    assert {c['id'] for c in selected}=={'park','mall','near-meal'}
    groups,missing=group_by_parking(selected,parks)
    assert len(groups)==1 and not missing
    multi=[c for c in candidates if c['id']!='near-meal']
    assert prefer_single_parking(multi,parks,parks[0])==multi


def test_parking_groups_require_actual_1000m_coverage_and_use_multiple_carparks():
    parks=[place('p1','parking'),place('p2','parking',lon=114.2)]
    stops=[{'id':'s1','place':place('s1','pet_parks'),'purpose':'park'},
           {'id':'s2','place':place('s2','restaurants',lon=114.201),'purpose':'meal'},
           {'id':'far','place':place('far','pet_parks',lon=114.3),'purpose':'park'}]
    groups,missing=group_by_parking(stops,parks)
    assert len(groups)==2 and [s['id'] for s in missing]==['far']
    assert all(distance(s['place'],g['parking'])<=1000 for g in groups for s in g['stops'])
    assert all('mall_policy_summary' not in s for g in groups for s in g['stops'])


def test_candidates_respect_date_region_sushi_and_unverified_google_match():
    request=PlanRequest(date='2026-10-26',region='hong_kong_island',interests=['park','activity'],cuisine='sushi')
    anchor=place('pet_parks:18','pet_parks');destination={**anchor,'anchor_place_ids':[anchor['id']]}
    rows=[anchor,place('sushi','restaurants',cuisines=['日式']),
          place('candidate','restaurants',cuisines=['日式'],restaurant_details={'match_status':'needs_review'}),
          place('other-region','pet_parks',district='九龍城區')]
    activities=[{'id':'old','place_id':anchor['id'],'start_date':'2026-01-01','end_date':'2026-01-02'},
                {'id':'future','place_id':anchor['id'],'start_date':'2027-01-01'},
                {'id':'today','place_id':anchor['id'],'start_date':'2026-10-26','end_date':'2026-10-26'}]
    candidates,_=build_candidates(rows,activities,[place('p','parking')],request,destination)
    assert {c['id'] for c in candidates}=={'pet_parks:18','sushi','activity:today'}


def test_plan_repairs_missing_modules_without_trusting_agent_ids_and_uses_actual_summary():
    rows=[place('pet_parks:18','pet_parks'),place('sushi','restaurants',cuisines=['日式']),
          place('mall','malls',notes=['Use a carrier in designated indoor areas.'])]
    class Pets:
        def places(self):return {'items':rows}
        def activities(self):return {'items':[]}
    class Parking:
        async def list(self,**kwargs):return {'status':'ready','items':[place('p','parking')]}
    container=SimpleNamespace(pets=Pets(),parking=Parking(),settings=SimpleNamespace(model='test'))
    async def selector(request,destination,candidates,settings):
        assert request['date']=='2026-10-26'
        return ['fake-id','pet_parks:18','pet_parks:18']
    result=asyncio.run(create_plan(container,PlanRequest(date='2026-10-26',region='hong_kong_island',
         destination_id='central-waterfront',interests=['park','mall'],cuisine='japanese'),selector))
    stops=[s for g in result['parking_groups'] for s in g['stops']]
    assert {s['purpose'] for s in stops}=={'park','mall','meal'}
    assert len(stops)==3 and 'fake-id' not in result['summary']
    assert all(('mall_policy_summary' in s)==(s['purpose']=='mall') for s in stops)
    assert result['status']=='ready'


def test_random_plan_stays_in_selected_region_and_unknown_destination_rejected():
    rows=[place('pet_parks:18','pet_parks'),place('pet_parks:52','pet_parks',district='屯門區')]
    class Parking:
        async def list(self,**kwargs):return {'status':'ready','items':[place('p','parking')]}
    pets=SimpleNamespace(places=lambda:{'items':rows},activities=lambda:{'items':[]})
    container=SimpleNamespace(pets=pets,parking=Parking(),settings=SimpleNamespace(model='test'))
    async def select(request,destination,candidates,settings):
        assert destination['region']=='hong_kong_island'
        return [candidates[0]['id']]
    result=asyncio.run(create_plan(container,PlanRequest(date='2026-10-26',region='hong_kong_island',random=True),select))
    assert result['destination']['id']=='central-waterfront'
    with pytest.raises(ValueError):
        asyncio.run(create_plan(container,PlanRequest(date='2026-10-26',region='hong_kong_island',destination_id='lam-tei'),select))


def test_any_cuisine_includes_a_meal_and_selected_area_does_not_cross_regions():
    request=PlanRequest(date='2026-10-27',region='any',cuisine='')
    anchor=place('pet_parks:18','pet_parks')
    destination={**anchor,'region':'hong_kong_island','anchor_place_ids':[anchor['id']]}
    rows=[anchor,place('meal','restaurants',cuisines=['西式']),
          place('opposite-shore','restaurants',lat=22.295,district='油尖旺區',cuisines=['西式'])]
    candidates,_=build_candidates(rows,[],[place('p','parking')],request,destination)
    assert {c['id'] for c in candidates}=={'pet_parks:18','meal'}


def test_local_area_cap_keeps_districts_and_interests_represented():
    rows=[place(f'park-{i}','pet_parks') for i in range(100)]
    rows += [place('kowloon','pet_parks',district='九龍城區'),
             place('new-territories','vets',district='屯門區')]
    request=PlanRequest(date='2026-10-27',interests=['park','vet'])
    result=local_areas(rows,[],request)
    assert len(result)==80
    assert {'area:kowloon','area:new-territories'}.issubset({r['id'] for r in result})


def test_nonrandom_plan_uses_real_local_area_outside_the_random_templates():
    rows=[place('new-vet','vets'),place('meal','restaurants',cuisines=['日式'])]
    class Parking:
        async def list(self,**kwargs):return {'status':'ready','items':[place('p','parking')]}
    pets=SimpleNamespace(places=lambda:{'items':rows},activities=lambda:{'items':[]})
    container=SimpleNamespace(pets=pets,parking=Parking(),settings=SimpleNamespace(model='test'))
    async def select(request,destination,candidates,settings):
        return ['new-vet']
    result=asyncio.run(create_plan(container,PlanRequest(date='2026-10-27',region='hong_kong_island',interests=['vet']),select))
    assert result['destination']['id']=='area:new-vet'
    assert {s['purpose'] for g in result['parking_groups'] for s in g['stops']}=={'vet','meal'}


def test_sushi_and_japanese_use_the_same_canonical_cuisine():
    anchor=place('pet_parks:18','pet_parks');destination={**anchor,'anchor_place_ids':[anchor['id']]}
    rows=[anchor,place('yakitori','restaurants',name='Yakitori Garden',cuisines=['日式']),
          place('sushi','restaurants',name='Sushi Place',cuisines=['日式']),
          place('thai','restaurants',cuisines=['泰式'])]
    results=[]
    for cuisine in ['sushi','壽司','寿司','japanese','日式']:
        candidates,_=build_candidates(rows,[],[place('p','parking')],PlanRequest(date='2026-10-27',cuisine=cuisine),destination)
        results.append({c['id'] for c in candidates if c['purpose']=='meal'})
    assert all(ids=={'yakitori','sushi'} for ids in results)


def test_every_catalogue_cuisine_can_filter_plan_meals():
    from backend.app.data.sources import CUISINES
    anchor=place('pet_parks:18','pet_parks');destination={**anchor,'anchor_place_ids':[anchor['id']]}
    for cuisine in CUISINES:
        rows=[anchor,place('match','restaurants',cuisines=[] if cuisine=='未分類' else [cuisine]),
              place('other','restaurants',cuisines=['different'])]
        candidates,_=build_candidates(rows,[],[place('p','parking')],PlanRequest(date='2026-10-27',cuisine=cuisine),destination)
        assert {c['id'] for c in candidates if c['purpose']=='meal'}=={'match'}, cuisine


def test_parking_sequence_keeps_meal_group_and_meal_stop_last():
    parking=[place('p1','parking'),place('p2','parking',lon=114.2)]
    stops=[{'id':'meal','purpose':'meal','place':place('meal','restaurants')},
           {'id':'mall','purpose':'mall','place':place('mall','malls')},
           {'id':'park','purpose':'park','place':place('park','pet_parks',lon=114.2)}]
    groups,remaining=group_by_parking(stops,parking)
    assert not remaining
    assert [s['purpose'] for g in groups for s in g['stops']]==['park','mall','meal']


def test_plan_enforces_one_final_meal_for_merged_japanese_cuisine():
    rows=[place('pet_parks:18','pet_parks'),
          place('meal','restaurants',name='Sushi Restaurant',cuisines=['日式']),
          place('meal2','restaurants',name='Second Sushi Restaurant',cuisines=['日式'])]
    class Parking:
        async def list(self,**kwargs):return {'status':'ready','items':[place('p','parking')]}
    pets=SimpleNamespace(places=lambda:{'items':rows},activities=lambda:{'items':[]})
    container=SimpleNamespace(pets=pets,parking=Parking(),settings=SimpleNamespace(model='test'))
    async def select(*args):return ['meal','pet_parks:18','meal2']
    result=asyncio.run(create_plan(container,PlanRequest(date='2026-10-27',region='hong_kong_island',
                destination_id='central-waterfront',cuisine='sushi'),select))
    stops=[s for g in result['parking_groups'] for s in g['stops']]
    assert [s['purpose'] for s in stops]==['park','meal']
    assert stops[-1]['place']['cuisines']==['日式']
    assert not result['warnings']
