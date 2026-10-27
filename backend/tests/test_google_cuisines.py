import json
from backend.app.data.google_cuisines import attach_google_cuisines, cuisine, select_candidate
from backend.app.models.pet import Place


def restaurant(**kwargs):
    return Place(id='restaurant:test',category='restaurants',name='八海山日本料理',address='測試地址',source_url='https://example.com',source_name='test',**kwargs)


def record(pid='candidate',**details):
    return {'google_place_id':pid,'status':'ready','details':{'displayName':{'text':'八海山日本料理'},'primaryType':'japanese_restaurant','location':{'latitude':22.3,'longitude':114.17},**details}}


def test_reject_wrong_branch_parent_venue_and_ambiguous_candidates():
    p=restaurant(latitude=22.3,longitude=114.17)
    assert select_candidate(p,[record()])['cuisines']==['日式']
    assert select_candidate(p,[record(location={'latitude':22.4,'longitude':114.17})]) is None
    assert select_candidate(p,[record(primaryType='sports_complex')]) is None
    assert select_candidate(p,[record('a'),record('b')]) is None
    assert select_candidate(p,[record(displayName={'text':'另一間完全唔同嘅餐廳'})]) is None


def test_saved_categories_are_optional_and_keep_curated_sources(tmp_path):
    p=restaurant();curated=restaurant(cuisines=['中式'],cuisine_source='https://example.com/curated')
    path=tmp_path/'map.json'
    attach_google_cuisines([p],path);assert p.cuisines==[]
    path.write_text(json.dumps({'restaurants':{p.id:{'address':p.address,'cuisines':['日式'],'source_url':'https://maps.google.com/'}}}))
    attach_google_cuisines([p,curated],path)
    assert p.cuisines==['日式'];assert curated.cuisines==['中式']
    moved=restaurant(address_en='Changed')
    moved.address='另一地址';attach_google_cuisines([moved],path);assert moved.cuisines==[]


def test_primary_cuisine_and_generic_fallback():
    assert cuisine({'primaryType':'italian_restaurant','types':['restaurant','cafe']})=='意式／薄餅'
    assert cuisine({'primaryType':'restaurant','types':['restaurant']})=='其他餐廳'
    assert cuisine({'primaryType':'shopping_mall','types':['restaurant']}) is None


def test_secondary_restaurant_types_and_parent_venue_protection():
    assert cuisine({'primaryType':'food_store','types':['cafe','food_store']})=='咖啡／輕食'
    assert cuisine({'primaryType':'banquet_hall','types':['banquet_hall','dim_sum_restaurant','cantonese_restaurant']})=='港式'
    assert cuisine({'types':['cat_cafe','restaurant']})=='咖啡／輕食'
    assert cuisine({'primaryType':'irish_restaurant','types':['restaurant']})=='西式'
    assert cuisine({'primaryType':'hotel','types':['japanese_restaurant','restaurant']}) is None
    assert cuisine({'primaryType':'food_store','types':['store','food']}) is None
    assert cuisine({'primaryType':'fast_food_restaurant','types':['breakfast_restaurant','restaurant']})=='其他餐廳'


def test_reviewed_address_match_does_not_allow_moved_address_or_different_branch(tmp_path,monkeypatch):
    import backend.app.data.google_cuisines as module
    p=restaurant(latitude=22.3,longitude=114.17)
    r=record(displayName={'text':'Different language name'},formattedAddress='Exact shop 110')
    path=tmp_path/'reviewed.json';path.write_text(json.dumps({p.id:{'google_place_id':'candidate','source_address':p.address,'google_address':'Exact shop 110','max_distance_m':120,'evidence':'Same shop verified'}}))
    monkeypatch.setattr(module,'REVIEWED_PATH',path)
    result=select_candidate(p,[r]);assert result['match_method']=='address_reviewed'
    r['details']['formattedAddress']='Different shop 111';assert select_candidate(p,[r]) is None
    r['details']['formattedAddress']='Exact shop 110';p.address='Moved';assert select_candidate(p,[r]) is None


def test_google_labels_from_cache_are_replaced_but_curated_are_kept(tmp_path):
    p=restaurant(cuisines=['其他餐廳'],cuisine_source='https://maps.google.com/?cid=123')
    path=tmp_path/'map.json';path.write_text(json.dumps({'restaurants':{p.id:{'address':p.address,'cuisines':['素食'],'source_url':'https://maps.google.com/?cid=123'}}}))
    attach_google_cuisines([p],path);assert p.cuisines==['素食']
    p.address='Moved address';attach_google_cuisines([p],path);assert p.cuisines==[]


def test_relaxed_inclusion_returns_cuisine_but_keeps_unverified_status():
    from backend.app.data.google_cuisines import select_cuisine_candidate
    p=restaurant(latitude=22.3,longitude=114.17)
    far=record(displayName={'text':'Different name'},location={'latitude':22.4,'longitude':114.17})
    assert select_candidate(p,[far]) is None
    result=select_cuisine_candidate(p,[far])
    assert result['cuisines']==['日式'] and result['match_status']=='needs_review'
    assert result['distance_m']>1000
    assert select_cuisine_candidate(p,[record(primaryType='hotel')]) is None
    assert select_cuisine_candidate(p,[]) is None
    near=record('nearby',displayName={'text':'Different name'})
    assert select_cuisine_candidate(p,[far,near])['google_place_id']=='nearby'
