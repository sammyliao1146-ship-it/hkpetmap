"""Download one image per already-matched facility. Manual/resumable only."""
import asyncio,hashlib,json,os,re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'data/google-facility-photos'
def now():return datetime.now(timezone.utc).isoformat()
def write(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
async def main():
 key=os.getenv('GOOGLE_PLACE_API_KEY') or dotenv_values(ROOT/'.env').get('GOOGLE_PLACE_API_KEY')
 if not key:raise SystemExit('Missing GOOGLE_PLACE_API_KEY')
 audit=json.loads((BASE/'index.json').read_text());target={k:r for k,r in audit['facilities'].items() if r['status']=='matched_with_photos'}
 (BASE/'photos').mkdir(exist_ok=True)
 out=BASE/'downloads.json';old=json.loads(out.read_text()) if out.exists() else {};rows=old.get('facilities',{});assets=old.get('assets',{})
 doc={'schema_version':1,'automatic_updates':False,'created_at':old.get('created_at',now()),'facilities':rows,'assets':assets}
 sem=asyncio.Semaphore(6);fatal=asyncio.Event();counts=Counter()
 async with httpx.AsyncClient(timeout=40,follow_redirects=True) as client:
  async def api(url,**kwargs):
   for attempt in range(4):
    r=await client.get(url,headers={'X-Goog-Api-Key':key},**kwargs)
    if r.status_code in (401,403):fatal.set()
    if r.status_code==429 or r.status_code>=500:
     if attempt<3:await asyncio.sleep(2**attempt);continue
    r.raise_for_status();return r
  async def download(rid,row):
   selected=next(c for c in row['candidates'] if c['google_place_id']==row['selected_google_place_id']);pid=selected['google_place_id']
   token=hashlib.sha256((rid+'|'+pid).encode()).hexdigest()[:24]
   saved=rows.get(rid,{})
   if saved.get('status')=='ready' and saved.get('google_place_id')==pid and (BASE/saved['local_path']).is_file():counts['reused']+=1;return
   async with sem:
    if fatal.is_set():return
    entry={'facility_id':rid,'name':row['name'],'address':row['address'],'category':row['category'],'google_place_id':pid,'google_name':selected['google_name'],'google_address':selected['google_address'],'token':token,'status':'error','fetched_at':now()}
    try:
     photo=selected['photo'];counts['media_requests']+=1
     media=await client.get('https://places.googleapis.com/v1/'+photo['name']+'/media',headers={'X-Goog-Api-Key':key},params={'maxWidthPx':800,'skipHttpRedirect':'true'})
     if media.status_code in (400,404):
      # Expired photo resource: refresh the reference only for this same place.
      fresh=await api('https://places.googleapis.com/v1/places/'+pid,params={'fields':'id,photos'});counts['photo_reference_refreshes']+=1
      photos=fresh.json().get('photos',[])
      if not photos:raise ValueError('No photo available for selected place')
      photo=photos[0];counts['media_requests']+=1
      media=await api('https://places.googleapis.com/v1/'+photo['name']+'/media',params={'maxWidthPx':800,'skipHttpRedirect':'true'})
     if media.status_code in (401,403):fatal.set()
     media.raise_for_status();uri=media.json()['photoUri']
     img=await client.get(uri);img.raise_for_status();ctype=img.headers.get('content-type','').split(';')[0]
     if not ctype.startswith('image/') or not img.content:raise ValueError('Non-image response')
     ext={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','image/avif':'.avif'}.get(ctype,'.img');path=BASE/'photos'/f'{token}{ext}'
     tmp=path.with_suffix('.tmp');tmp.write_bytes(img.content);tmp.replace(path)
     entry.update(status='ready',local_path=str(path.relative_to(BASE)),content_type=ctype,bytes=len(img.content),photo=photo,source_url=photo.get('googleMapsUri') or selected['google_maps_url'])
     assets[token]={'facility_id':rid,'local_path':entry['local_path'],'content_type':ctype};counts['downloaded']+=1
    except Exception as e:
     entry['error']=type(e).__name__+(f' HTTP {e.response.status_code}' if isinstance(e,httpx.HTTPStatusError) else '');counts['errors']+=1
    rows[rid]=entry;write(out,doc)
    if len(rows)%25==0 or fatal.is_set():print(json.dumps({'processed':len(rows),'target':len(target),**counts,'fatal':fatal.is_set()}),flush=True)
  await asyncio.gather(*(download(rid,row) for rid,row in target.items()))
 doc['completed_at']=now();doc['summary']={'target':len(target),'statuses':dict(Counter(r['status'] for r in rows.values())),**counts};write(out,doc);print(json.dumps(doc['summary']),flush=True)
 if fatal.is_set():raise SystemExit('Stopped on API authorization error; partial downloads saved')
if __name__=='__main__':asyncio.run(main())
