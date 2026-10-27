import json
from backend.app.data.photos import allowed_photo, attach_photos, name_key, parse_lcsd_photos
from backend.app.models.pet import Place

PHOTO='https://www.lcsd.gov.hk/file_upload_clpss/leisure_facilities/en/common/images/facilities/facilitieslist/pet/2216_1.jpg'
SOURCE='https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/Details.do?ftid=47&did=1'


def test_photo_belongs_to_preceding_facility_table():
    html=f'''<table class="fac-table"><tr><td>場地名稱</td><td>加多近街花園</td></tr></table>
      <div class="photo_zone"><a class="cboxElement" href="{PHOTO}"><img src="{PHOTO}"></a></div>
      <table class="fac-table"><tr><td>場地名稱</td><td>另一個公園</td></tr></table>
      <div class="photo_zone"><a href="/logo.png"><img src="/logo.png"></a></div>'''
    result=parse_lcsd_photos(html,SOURCE)
    assert result[name_key('加多近街花園')][0]['url']==PHOTO
    assert name_key('另一個公園') not in result
    assert name_key('加多近街花園（指定位置）')==name_key('加多近街花園')
    assert allowed_photo(PHOTO)
    assert not allowed_photo(PHOTO.replace('www.lcsd.gov.hk','www.lcsd.gov.hk.evil.invalid'))
    assert not allowed_photo(PHOTO.replace('https://','https://user:password@'))
    assert not allowed_photo('http://127.0.0.1/image.jpg')


def test_manifest_uses_exact_place_id_and_keeps_restaurants_unchanged(tmp_path):
    records={'places':{'pet_parks:1':[{'url':PHOTO,'source_url':SOURCE,'credit':'康文署','alt':'公園實景'}]}}
    manifest=tmp_path/'photos.json';manifest.write_text(json.dumps(records))
    places=[Place(id=pid,category=category,name='同名場地',source_name='測試',source_url=SOURCE) for pid,category in [('pet_parks:1','pet_parks'),('pet_parks:2','pet_parks'),('restaurant:1','restaurants')]]
    attach_photos(places,manifest)
    assert len(places[0].photos)==1
    assert places[1].photos==[] and places[2].photos==[]
