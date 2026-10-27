"""Resolve restaurant Google Place ID candidates; IDs-only Text Search, resumable."""
import asyncio, csv, json, os
from pathlib import Path
from datetime import datetime, timezone
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/google-restaurant-place-ids.json'

def save(rows,total):
    payload={'updated_at':datetime.now(timezone.utc).isoformat(),'total_restaurants':total,'field_mask':'places.id','matching_note':'Google text-search candidates from name and address; not independently verified.','restaurants':rows}
    tmp=OUT.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2));tmp.replace(OUT)
    with OUT.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['id','name','address','licence_number','google_place_id','status','candidate_place_ids','query','error'])
        writer.writeheader()
        for row in rows.values(): writer.writerow({**row,'candidate_place_ids':'|'.join(row['candidate_place_ids'])})

async def main():
    key=os.environ.get('GOOGLE_PLACE_API_KEY') or dotenv_values(ROOT/'.env').get('GOOGLE_PLACE_API_KEY')
    if not key: raise SystemExit('GOOGLE_PLACE_API_KEY missing')
    places=[p for p in json.loads((ROOT/'data/pet-snapshot.json').read_text())['places'] if p['category']=='restaurants']
    rows=json.loads(OUT.read_text())['restaurants'] if OUT.exists() else {}
    sem=asyncio.Semaphore(5); fatal=asyncio.Event(); requests=0
    async with httpx.AsyncClient(timeout=35,headers={'X-Goog-Api-Key':key,'X-Goog-FieldMask':'places.id'}) as client:
        async def fetch(p):
            nonlocal requests
            if p['id'] in rows and rows[p['id']]['status']!='error': return
            async with sem:
                if fatal.is_set(): return
                row={k:p.get(k) for k in ['id','name','address','licence_number']}
                row.update(google_place_id=None,status='no_result',candidate_place_ids=[],query='',error='')
                queries=[f"{p['name']} {p.get('address') or ''} 香港"]
                if p.get('name_en') and p.get('address_en'): queries.append(f"{p['name_en']} {p['address_en']} Hong Kong")
                try:
                    for query in dict.fromkeys(queries):
                        row['query']=query
                        for attempt in range(4):
                            requests+=1
                            r=await client.post('https://places.googleapis.com/v1/places:searchText',json={'textQuery':query,'regionCode':'HK','languageCode':'zh-TW','pageSize':3})
                            if r.status_code==429 or r.status_code>=500:
                                if attempt<3: await asyncio.sleep(2**attempt);continue
                            break
                        if r.status_code in (400,401,403): fatal.set()
                        r.raise_for_status()
                        ids=list(dict.fromkeys(x['id'] for x in r.json().get('places',[]) if x.get('id')))
                        row['candidate_place_ids']=ids
                        if ids:
                            row['status']='single_candidate' if len(ids)==1 else 'needs_review'
                            if len(ids)==1: row['google_place_id']=ids[0]
                            break
                except Exception as e:
                    row['status']='error'; row['error']=type(e).__name__
                    if isinstance(e,httpx.HTTPStatusError): row['error']+=f' HTTP {e.response.status_code}: '+e.response.text[:700].replace(key,'[REDACTED]')
                rows[p['id']]=row
                save(rows,len(places))
                if len(rows)%25==0 or fatal.is_set(): print(json.dumps({'processed':len(rows),'total':len(places),'requests':requests,'fatal':fatal.is_set()},ensure_ascii=False),flush=True)
        await asyncio.gather(*(fetch(p) for p in places))
    save(rows,len(places))
    from collections import Counter
    print(json.dumps({'processed':len(rows),'total':len(places),'requests':requests,'statuses':dict(Counter(r['status'] for r in rows.values()))},ensure_ascii=False),flush=True)

if __name__=='__main__': asyncio.run(main())
