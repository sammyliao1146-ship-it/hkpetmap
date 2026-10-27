"""Manual one-time collection. No timers or startup hooks; existing successes are reused."""
import asyncio, argparse, json, os, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/google-places'
FIELDS=','.join('id displayName formattedAddress location primaryType primaryTypeDisplayName types rating userRatingCount websiteUri nationalPhoneNumber internationalPhoneNumber regularOpeningHours businessStatus googleMapsUri googleMapsLinks photos reviews reservable priceLevel priceRange editorialSummary allowsDogs outdoorSeating dineIn takeout delivery servesVegetarianFood servesBreakfast servesLunch servesDinner servesBrunch servesBeer servesWine servesCocktails servesDessert servesCoffee menuForChildren goodForChildren goodForGroups paymentOptions parkingOptions accessibilityOptions attributions movedPlaceId'.split())
def now(): return datetime.now(timezone.utc).isoformat()
def write(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def safe_error(e):
    # Exception URLs can contain signed photo URIs. Never persist them.
    return type(e).__name__+(f' HTTP {e.response.status_code}' if isinstance(e,httpx.HTTPStatusError) else '')
def public_https(url):
    p=urlsplit(url)
    return p.scheme in ('http','https') and p.hostname and p.hostname not in ('localhost','127.0.0.1','::1')
def links(html,base):
    soup=BeautifulSoup(html,'html.parser');found={'booking':[],'menu':[]}
    for a in soup.select('a[href]'):
        href=urljoin(base,a.get('href',''));label=a.get_text(' ',strip=True)[:200]
        if not public_https(href): continue
        for kind,pattern in [('booking',r'reserv|book.?now|book.?table|inline\.app/booking|訂位|訂座|预订|預訂|訂枱'),('menu',r'\bmenu\b|a.la.carte|菜單|餐牌|菜单|餐单|餐單')]:
            if re.search(pattern,label+' '+href,re.I) and href not in [x['url'] for x in found[kind]]:
                found[kind].append({'url':href,'label':label,'source_url':base,'discovery':'official_website_anchor'})
    return {k:v[:20] for k,v in found.items()}
async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--retry-errors',action='store_true');args=parser.parse_args()
    key=os.environ.get('GOOGLE_PLACE_API_KEY') or dotenv_values(ROOT/'.env').get('GOOGLE_PLACE_API_KEY')
    if not key: raise SystemExit('GOOGLE_PLACE_API_KEY missing')
    BASE.mkdir(parents=True,exist_ok=True);(BASE/'places').mkdir(exist_ok=True);(BASE/'photos').mkdir(exist_ok=True)
    source=json.loads((ROOT/'data/google-restaurant-place-ids.json').read_text());restaurants=source['restaurants'];refs={}
    for rid,row in restaurants.items():
        for pid in row['candidate_place_ids']: refs.setdefault(pid,[]).append(rid)
    index={'schema_version':1,'created_at':now(),'automatic_updates':False,'refresh_policy':'manual_only; reuse saved records; no expiry-triggered refresh','field_mask':FIELDS,'photo_limit':1,'language':'zh-TW','restaurants':restaurants,'places':{}}
    manifest=BASE/'index.json';sem=asyncio.Semaphore(6);fatal=asyncio.Event();stats=Counter()
    async with httpx.AsyncClient(timeout=30,follow_redirects=True) as client:
        async def google_get(url,**kw):
            for attempt in range(4):
                r=await client.get(url,headers={'X-Goog-Api-Key':key},**kw)
                if r.status_code in (400,401,403): fatal.set()
                if r.status_code==429 or r.status_code>=500:
                    if attempt<3: await asyncio.sleep(2**attempt);continue
                r.raise_for_status();return r
        async def fetch(pid,rids):
            async with sem:
                path=BASE/'places'/f'{pid}.json'
                if path.exists():
                    old=json.loads(path.read_text())
                    if old.get('status')=='ready' or not args.retry_errors:
                        index['places'][pid]={'path':str(path.relative_to(BASE)),'status':old['status'],'restaurant_ids':rids};stats['reused']+=1;return
                if fatal.is_set(): return
                record={'google_place_id':pid,'restaurant_ids':rids,'fetched_at':now(),'automatic_updates':False,'status':'error','details':None,'photo':None,'website_links':{'booking':[],'menu':[]},'errors':{}}
                try:
                    r=await google_get('https://places.googleapis.com/v1/places/'+pid,params={'languageCode':'zh-TW','fields':FIELDS});data=r.json()
                    photo=(data.pop('photos',[]) or [None])[0]
                    record['details']=data;record['status']='ready';stats['details_ok']+=1
                    record['cuisine']={'primary_type':data.get('primaryType'),'label':data.get('primaryTypeDisplayName',{}).get('text'),'types':data.get('types',[]),'source':'Google place types, not a full cuisine taxonomy'}
                    record['booking_url']=None;record['menu_url']=None
                    if photo:
                        record['photo']={'metadata':photo,'local_path':None,'status':'error'}
                        try:
                            # One media request; one image. API key header stays on Google request only.
                            media=await google_get('https://places.googleapis.com/v1/'+photo['name']+'/media',params={'maxWidthPx':800,'skipHttpRedirect':'true'})
                            uri=media.json()['photoUri']
                            record['photo']['photo_uri']=uri
                            img=await client.get(uri);img.raise_for_status()
                            ctype=img.headers.get('content-type','').split(';')[0]
                            if not ctype.startswith('image/'): raise ValueError('Non-image response')
                            ext={'image/png':'.png','image/webp':'.webp','image/jpeg':'.jpg','image/avif':'.avif'}.get(ctype,'.img')
                            target=BASE/'photos'/f'{pid}{ext}';target.write_bytes(img.content)
                            record['photo'].update(local_path=str(target.relative_to(BASE)),status='ready',content_type=ctype,bytes=len(img.content));stats['photos_ok']+=1
                        except Exception as e: record['errors']['photo']=safe_error(e);stats['photo_errors']+=1
                    else: stats['no_photo']+=1
                    site=data.get('websiteUri')
                    if site and public_https(site):
                        try:
                            async with client.stream('GET',site,timeout=12,headers={'User-Agent':'HKPetFinder/0.1 (manual restaurant link collection)'}) as web:
                                web.raise_for_status()
                                if 'html' in web.headers.get('content-type',''):
                                    content=bytearray()
                                    async for chunk in web.aiter_bytes():
                                        content.extend(chunk)
                                        if len(content)>2000000: break
                                    record['website_links']=links(bytes(content),str(web.url))
                                    for kind in ('booking','menu'):
                                        if record['website_links'][kind]: record[kind+'_url']=record['website_links'][kind][0]['url'];stats[kind+'_found']+=1
                        except Exception as e: record['errors']['website']=safe_error(e)
                except Exception as e:
                    record['errors']['details']=safe_error(e);stats['details_errors']+=1
                write(path,record)
                index['places'][pid]={'path':str(path.relative_to(BASE)),'status':record['status'],'restaurant_ids':rids}
                if len(index['places'])%25==0:
                    write(manifest,index);print(json.dumps({'processed':len(index['places']),'total':len(refs),**stats},ensure_ascii=False),flush=True)
        await asyncio.gather(*(fetch(pid,rids) for pid,rids in refs.items()))
    index['completed_at']=now();index['summary']={'unique_candidate_ids':len(refs),'saved':len(index['places']),**stats};write(manifest,index)
    print(json.dumps(index['summary'],ensure_ascii=False),flush=True)
    if len(index['places'])<len(refs): raise SystemExit('Stopped on API authorization/configuration error. Saved partial results.')
if __name__=='__main__': asyncio.run(main())
