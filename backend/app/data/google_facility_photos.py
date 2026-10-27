"""Serve downloaded, matched facility photos from disk; no live API calls."""
import json,re
from pathlib import Path
from pydantic import HttpUrl
ROOT=Path(__file__).resolve().parents[3];BASE=ROOT/'data/google-facility-photos'

def photo_path(token,base=None):
 base=Path(base) if base else BASE
 if not re.fullmatch(r'[0-9a-f]{24}',token):return None
 try:
  data=json.loads((base/'downloads.json').read_text());asset=data.get('assets',{}).get(token)
  if not asset:return None
  row=data.get('facilities',{}).get(asset['facility_id'],{})
  if row.get('status')!='ready' or row.get('token')!=token or row.get('local_path')!=asset.get('local_path'):return None
  path=(base/asset['local_path']).resolve()
  return path if path.is_relative_to((base/'photos').resolve()) and path.is_file() else None
 except (OSError,ValueError,KeyError,TypeError):return None

def attach_google_facility_photos(places,base=None):
 base=Path(base) if base else BASE
 try:data=json.loads((base/'downloads.json').read_text());rows=data['facilities']
 except (OSError,ValueError,KeyError,TypeError):return
 from backend.app.models.pet import PlacePhoto
 for place in places:
  if place.category=='restaurants' or place.photos:continue
  row=rows.get(place.id)
  if not row or row.get('status')!='ready' or row.get('address')!=place.address:continue
  token=row.get('token','');asset=data.get('assets',{}).get(token,{})
  if not re.fullmatch(r'[0-9a-f]{24}',token) or asset.get('facility_id')!=place.id:continue
  path=(base/row['local_path']).resolve()
  if not path.is_relative_to((base/'photos').resolve()) or not path.is_file():continue
  try:
   authors=row.get('photo',{}).get('authorAttributions',[])
   place.photos=[PlacePhoto(url=f'/api/v1/facility-photos/{token}',source_url=row['source_url'],credit='Google Maps',alt=place.name+'・場地相片',authors=authors)]
  except (ValueError,KeyError,TypeError):continue
