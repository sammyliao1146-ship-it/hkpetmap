"""Manual Google photo availability audit for facilities with no existing photos."""
import asyncio,json,os,re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import httpx
from dotenv import dotenv_values
from backend.app.models.pet import Snapshot
from backend.app.data.photos import attach_photos
from backend.app.data.google_cuisines import similarity,distance
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'data/google-facility-photos'
FIELDS='id,displayName,formattedAddress,location,primaryType,types,photos,googleMapsUri'
def now():return datetime.now(timezone.utc).isoformat()
def write(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2));t.replace(p)
async def main():
 key=os.getenv('GOOGLE_PLACE_API_KEY') or dotenv_values(ROOT/'.env').get('GOOGLE_PLACE_API_KEY')
 if not key:raise SystemExit('Missing GOOGLE_PLACE_API_KEY')
 BASE.mkdir(parents=True,exist_ok=True);(BASE/'places').mkdir(exist_ok=True)
 s=Snapshot.model_validate_json((ROOT/'data/pet-snapshot.json').read_text());attach_photos(s.places)
 places=[p for p in s.places if p.category!='restaurants' and not p.photos]
 out=BASE/'index.json';old=json.loads(out.read_text()) if out.exists() else {};rows=old.get('facilities',{})
 summary={'created_at':now(),'automatic_updates':False,'scope':'facilities without existing photos; photo metadata only; no photo media download','total_facilities_without_photos':len(places),'facilities':rows}
 sem=asyncio.Semaphore(6);fatal=asyncio.Event();locks={};stats=Counter()
 async with httpx.AsyncClient(timeout=35) as client:
  async def request(method,url,**kwargs):
   for attempt in range(4):
    r=await client.request(method,url,headers={'X-Goog-Api-Key':key},**kwargs)
    if r.status_code in (400,401,403):fatal.set()
    if r.status_code==429 or r.status_code>=500:
     if attempt<3:await asyncio.sleep(2**attempt);continue
    r.raise_for_status();return r
  async def details(pid):
   if not re.fullmatch(r'[A-Za-z0-9_-]{5,200}',pid):raise ValueError('Invalid ID')
   async with locks.setdefault(pid,asyncio.Lock()):
    path=BASE/'places'/f'{pid}.json'
    if path.exists():return json.loads(path.read_text())
    stats['details_requests']+=1
    r=await request('GET','https://places.googleapis.com/v1/places/'+pid,params={'languageCode':'zh-TW','fields':FIELDS})
    d=r.json();d['photo_count']=len(d.get('photos',[]));d['photos']=d.get('photos',[])[:1];d['fetched_at']=now();write(path,d);return d
  async def check(p):
   if p.id in rows and rows[p.id].get('status')!='error':return
   async with sem:
    if fatal.is_set():return
    row={'id':p.id,'name':p.name,'name_en':p.name_en,'category':p.category,'address':p.address,'checked_at':now(),'status':'no_result','candidates':[],'selected_google_place_id':None}
    try:
     queries=[f"{p.name} {p.address or p.district or ''} 香港"]
     if p.name_en and p.name_en!=p.name:queries.append(f"{p.name_en} {p.address_en or p.address or ''} Hong Kong")
     ids=[]
     for q in dict.fromkeys(queries):
      payload={'textQuery':q,'regionCode':'HK','languageCode':'zh-TW','pageSize':2}
      if p.latitude is not None and p.longitude is not None:payload['locationBias']={'circle':{'center':{'latitude':p.latitude,'longitude':p.longitude},'radius':1500}}
      stats['search_requests']+=1
      # IDs-only search; details requested separately to verify candidate and photos.
      r=await request('POST','https://places.googleapis.com/v1/places:searchText',json=payload,params={'fields':'places.id'})
      ids=[x['id'] for x in r.json().get('places',[]) if x.get('id')]
      row['query']=q
      if ids:break
     for rank,pid in enumerate(dict.fromkeys(ids)):
      if fatal.is_set():break
      d=await details(pid);sim=similarity(p,d);meters=distance(p,d)
      matched=(meters is not None and ((meters<=200 and sim>=.5) or (meters<=500 and sim>=.85) or (p.category in {'parks','pet_parks','inclusive_parks'} and meters<=1000 and sim>=.9))) or (meters is None and sim>=.9)
      score=sim+(.3/(1+meters/200) if meters is not None else 0)-rank*.001
      row['candidates'].append({'google_place_id':pid,'google_name':d.get('displayName',{}).get('text'),'google_address':d.get('formattedAddress'),'primary_type':d.get('primaryType'),'photo_count':d.get('photo_count',0),'photo':next(iter(d.get('photos',[])),None),'google_maps_url':d.get('googleMapsUri'),'name_similarity':round(sim,3),'distance_m':round(meters,1) if meters is not None else None,'matched':matched,'score':round(score,4)})
     candidates=sorted(row['candidates'],key=lambda d:d['score'],reverse=True);trusted=[x for x in candidates if x['matched']]
     if trusted:
      first=trusted[0];ambiguous=len(trusted)>1 and first['score']-trusted[1]['score']<.12
      if not ambiguous:
       row['selected_google_place_id']=first['google_place_id'];row['status']='matched_with_photos' if first['photo_count'] else 'matched_without_photos'
      else:row['status']='needs_review_with_photos' if any(x['photo_count'] for x in trusted) else 'needs_review_without_photos'
     elif candidates:row['status']='needs_review_with_photos' if any(x['photo_count'] for x in candidates) else 'needs_review_without_photos'
    except Exception as e:
     row['status']='error';row['error']=type(e).__name__+(f' HTTP {e.response.status_code}' if isinstance(e,httpx.HTTPStatusError) else '')
    rows[p.id]=row
    write(out,summary)
    if len(rows)%25==0 or fatal.is_set():print(json.dumps({'processed':len(rows),'total':len(places),**stats,'fatal':fatal.is_set()}),flush=True)
  await asyncio.gather(*(check(p) for p in places))
 summary['completed_at']=now();summary['statuses']=dict(Counter(r['status'] for r in rows.values()));summary['by_category']={c:dict(Counter(r['status'] for r in rows.values() if r['category']==c)) for c in sorted({p.category for p in places})};summary['request_counts_this_run']=dict(stats);write(out,summary)
 print(json.dumps({'processed':len(rows),'total':len(places),'statuses':summary['statuses'],'by_category':summary['by_category'],'requests':dict(stats)},ensure_ascii=False),flush=True)
 if fatal.is_set():raise SystemExit('API authorization/configuration error. Partial results saved.')
if __name__=='__main__':asyncio.run(main())
