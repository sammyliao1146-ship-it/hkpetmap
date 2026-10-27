import json
from backend.app.data.restaurant_details import attach_restaurant_details, photo_path
from backend.app.models.pet import Place


def test_local_profile_join_missing_fields_and_photo_safety(tmp_path):
    (tmp_path/'places').mkdir();(tmp_path/'photos').mkdir()
    pid='testPlace123';image=tmp_path/'photos'/f'{pid}.jpg';image.write_bytes(b'image')
    record={'status':'ready','details':{'rating':3.8,'userRatingCount':92,'priceLevel':'PRICE_LEVEL_MODERATE'},'photo':{'status':'ready','local_path':f'photos/{pid}.jpg','metadata':{'authorAttributions':[{'displayName':'Photographer'}]}}}
    path=tmp_path/'places'/f'{pid}.json';path.write_text(json.dumps(record))
    manifest=tmp_path/'map.json';manifest.write_text(json.dumps({'restaurants':{'restaurant:test':{'address':'Test address','google_place_id':pid}}}))
    p=Place(id='restaurant:test',category='restaurants',name='Test',address='Test address',source_url='https://example.com',source_name='test')
    attach_restaurant_details([p],manifest,tmp_path)
    assert p.restaurant_details.rating==3.8
    assert p.restaurant_details.photo_credit=='Photographer'
    assert p.restaurant_details.photo_url.endswith(pid)
    assert p.restaurant_details.menu_url is None and p.restaurant_details.reservable is None
    assert photo_path(pid,tmp_path)==image
    assert photo_path('../map',tmp_path) is None
    record['photo']['local_path']='../map.json';path.write_text(json.dumps(record));assert photo_path(pid,tmp_path) is None
    p.address='Different branch';attach_restaurant_details([p],manifest,tmp_path);assert p.restaurant_details is None


def test_dish_photo_only_serves_visually_selected_image_inside_directory(tmp_path):
    from backend.app.data.restaurant_details import dish_photo_path
    pid='testPlace123';folder=tmp_path/'dish-photos';folder.mkdir();image=folder/'dish.jpg';image.write_bytes(b'image')
    row={'local_path':'dish-photos/dish.jpg','visual_review':'food'}
    manifest=folder/'selected.json';manifest.write_text(json.dumps({'places':{pid:row}}))
    assert dish_photo_path(pid,tmp_path)==image
    row['visual_review']='interior';manifest.write_text(json.dumps({'places':{pid:row}}));assert dish_photo_path(pid,tmp_path) is None
    row.update(visual_review='food',local_path='../secret.jpg');manifest.write_text(json.dumps({'places':{pid:row}}));assert dish_photo_path(pid,tmp_path) is None
    assert dish_photo_path('../selected',tmp_path) is None
