"""Download additional photo candidates for manual visual dish selection; no scheduler."""
import asyncio,json,os
from pathlib import Path
from datetime import datetime,timezone
from dotenv import dotenv_values
import httpx
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'data/google-places';DEST=BASE/'dish-photos'
def write(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2));t.replace(p)
async def main():
 key=os.getenv('GOOGLE_PLACE_API_KEY') or dotenv_values(ROOT/'.env')['GOOGLE_PLACE_API_KEY'];DEST.mkdir(exist_ok=True);index=DEST/'candidates.json';saved=json.loads(index.read_text()) if index.exists() else {};rows=saved.get('places',{})
 mapping=json.loads((BASE/'cuisine-map.json').read_text())['restaurants'];pids=sorted({r['google_place_id'] for r in mapping.values()});targets=[]
 for pid in pids:
  r=json.loads((BASE/'places'/f'{pid}.json').read_text());d=r['details']
  if d.get('rating',0)>=4.5 and d.get('userRatingCount',0)>=20:targets.append((pid,r))
 doc={'automatic_updates':False,'criteria':{'min_rating':4.5,'min_rating_count':20},'places':rows};sem=asyncio.Semaphore(6)
 async with httpx.AsyncClient(timeout=40,follow_redirects=True) as client:
  async def api(url,params):
   for n in range(4):
    r=await client.get(url,params=params,headers={'X-Goog-Api-Key':key})
    if (r.status_code==429 or r.status_code>=500) and n<3:await asyncio.sleep(2**n);continue
    r.raise_for_status();return r
  async def fetch(pid,previous):
   if pid in rows and rows[pid].get('status')=='ready':return
   async with sem:
    d=previous['details'];r={'google_place_id':pid,'name':d.get('displayName',{}).get('text'),'rating':d['rating'],'rating_count':d['userRatingCount'],'status':'error','candidates':[]}
    try:
     data=(await api('https://places.googleapis.com/v1/places/'+pid,{'fields':'id,photos'})).json();photos=data.get('photos',[])
     old=(previous.get('photo') or {}).get('metadata',{});old_uri=old.get('googleMapsUri')
     candidates=[p for i,p in enumerate(photos) if i>0 and (not old_uri or p.get('googleMapsUri')!=old_uri)][:3]
     for number,photo in enumerate(candidates,1):
      try:
       media=await api('https://places.googleapis.com/v1/'+photo['name']+'/media',{'maxWidthPx':640,'skipHttpRedirect':'true'});uri=media.json()['photoUri'];img=await client.get(uri);img.raise_for_status();ctype=img.headers.get('content-type','').split(';')[0]
       if not ctype.startswith('image/'):raise ValueError('Non-image')
       ext={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp','image/avif':'.avif'}.get(ctype,'.img');path=DEST/f'{pid}-{number}{ext}';path.write_bytes(img.content)
       r['candidates'].append({'number':number,'local_path':str(path.relative_to(BASE)),'metadata':photo,'content_type':ctype,'bytes':len(img.content)})
      except Exception as e:r.setdefault('errors',[]).append(type(e).__name__)
     r['status']='ready';r['fetched_at']=datetime.now(timezone.utc).isoformat()
    except Exception as e:r['error']=type(e).__name__
    rows[pid]=r;write(index,doc)
    if len(rows)%20==0:print(json.dumps({'processed':len(rows),'total':len(targets)}),flush=True)
  await asyncio.gather(*(fetch(pid,r) for pid,r in targets))
 doc['completed_at']=datetime.now(timezone.utc).isoformat();write(index,doc);print(json.dumps({'places':len(rows),'candidates':sum(len(r['candidates']) for r in rows.values()),'errors':sum(r['status']=='error' for r in rows.values())}),flush=True)
if __name__=='__main__':asyncio.run(main())
