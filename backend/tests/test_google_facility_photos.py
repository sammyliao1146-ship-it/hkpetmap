import json
import pytest
from pydantic import ValidationError
from backend.app.data.google_facility_photos import photo_path,attach_google_facility_photos
from backend.app.models.pet import Place,PlacePhoto
TOKEN='a'*24
URL='https://maps.google.com/'

def fixture(tmp):
 (tmp/'photos').mkdir();p=tmp/'photos'/f'{TOKEN}.jpg';p.write_bytes(b'photo')
 d={'assets':{TOKEN:{'facility_id':'vets:test','local_path':f'photos/{TOKEN}.jpg'}},'facilities':{'vets:test':{'status':'ready','token':TOKEN,'address':'Test address','local_path':f'photos/{TOKEN}.jpg','source_url':URL,'photo':{'authorAttributions':[{'displayName':'Photographer','uri':URL}]}}}}
 (tmp/'downloads.json').write_text(json.dumps(d));return d,p

def test_facility_photo_only_for_same_id_address_and_empty_gallery(tmp_path):
 d,path=fixture(tmp_path)
 def place(pid='vets:test',**kw):return Place(id=pid,category='vets',name='Clinic',address='Test address',source_url=URL,source_name='test',**kw)
 p=place();other=place('vets:other');existing=place(photos=[PlacePhoto(url='https://example.com/photo.jpg',source_url=URL,credit='Official',alt='Photo')])
 attach_google_facility_photos([p,other,existing],tmp_path)
 assert p.photos[0].url==f'/api/v1/facility-photos/{TOKEN}'
 assert p.photos[0].authors[0]['displayName']=='Photographer'
 assert not other.photos;assert existing.photos[0].credit=='Official'
 moved=place();moved.address='Other address';attach_google_facility_photos([moved],tmp_path);assert not moved.photos
 assert photo_path(TOKEN,tmp_path)==path
 assert photo_path('../downloads',tmp_path) is None
 d['assets'][TOKEN]['local_path']='../outside.jpg';(tmp_path/'downloads.json').write_text(json.dumps(d));assert photo_path(TOKEN,tmp_path) is None

def test_photo_url_only_allows_expected_local_route():
 p=PlacePhoto(url=f'/api/v1/facility-photos/{TOKEN}',source_url=URL,credit='Google',alt='Photo');assert str(p.url).endswith(TOKEN)
 for url in ['/etc/passwd','/api/v1/facility-photos/../../secrets','/api/v1/restaurant-photos/test']:
  with pytest.raises(ValidationError):PlacePhoto(url=url,source_url=URL,credit='Google',alt='Photo')
