"""Repair website-link extraction only; never request Google or refresh place details."""
import asyncio,json
from pathlib import Path
import httpx
from scripts.fetch_google_place_details import BASE,links,write,safe_error
async def main():
 sem=asyncio.Semaphore(10);seen=set();count=0
 async with httpx.AsyncClient(timeout=12,follow_redirects=True) as client:
  async def repair(path):
   nonlocal count
   d=json.loads(path.read_text())
   if d.get('errors',{}).get('website')!='TypeError': return
   site=(d.get('details') or {}).get('websiteUri')
   if not site: return
   async with sem:
    try:
     async with client.stream('GET',site,headers={'User-Agent':'HKPetFinder/0.1 (manual restaurant link collection)'}) as r:
      r.raise_for_status()
      if 'html' in r.headers.get('content-type',''):
       data=bytearray()
       async for chunk in r.aiter_bytes():
        data.extend(chunk)
        if len(data)>2000000: break
       found=links(bytes(data),str(r.url));d['website_links']=found
       for kind in ('booking','menu'): d[kind+'_url']=found[kind][0]['url'] if found[kind] else None
      d['errors'].pop('website',None)
    except Exception as e: d['errors']['website']=safe_error(e)
    write(path,d);count+=1
  while True:
   paths=[p for p in (BASE/'places').glob('*.json') if p.name not in seen]
   seen.update(p.name for p in paths)
   await asyncio.gather(*(repair(p) for p in paths))
   index=BASE/'index.json'
   if index.exists() and json.loads(index.read_text()).get('completed_at'):
    # Final scan covers records created during the previous repair batch.
    extra=[p for p in (BASE/'places').glob('*.json') if p.name not in seen]
    await asyncio.gather(*(repair(p) for p in extra));break
   await asyncio.sleep(5)
 print(json.dumps({'website_parser_repairs':count}),flush=True)
if __name__=='__main__': asyncio.run(main())
