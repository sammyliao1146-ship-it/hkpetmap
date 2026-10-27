"""Match LCSD facility-page photographs to the same named place and district."""
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

MANIFEST = Path(__file__).with_name('facility_photos.json')
DISTRICTS = {'中西':1,'東':2,'離島':3,'九龍城':4,'葵青':5,'觀塘':6,'北':7,'西貢':8,'深水埗':9,'沙田':10,'南':11,'大埔':12,'荃灣':13,'屯門':14,'灣仔':15,'黃大仙':16,'油尖旺':17,'元朗':18}
FACILITY_TYPES = {'parks':3,'pet_parks':47,'inclusive_parks':165}


def name_key(value):
    value=unicodedata.normalize('NFKC',value or '')
    value=re.sub(r'\(指定(?:位置|範圍|地方|區域)\)', '', value)
    return re.sub(r'[\s、，,・·\-]','',value).casefold()


def district_id(value):
    return DISTRICTS.get((value or '').removesuffix('區'))


def allowed_photo(url):
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port or '\\' in url:
            return False
        path=unquote(parsed.path)
        if '..' in path.split('/'):
            return False
        return parsed.hostname=='www.lcsd.gov.hk' and path.startswith((
            '/file_upload_clpss/leisure_facilities/en/common/images/photo/facilities/',
            '/file_upload_clpss/leisure_facilities/en/common/images/facilities/facilitieslist/')) and path.lower().endswith(('.jpg','.jpeg','.png','.webp'))
    except ValueError:
        return False


def parse_lcsd_photos(html, source_url):
    soup=BeautifulSoup(html,'html.parser')
    result={}
    for gallery in soup.select('.photo_zone'):
        table=gallery.find_previous_sibling('table')
        if table is None:
            continue
        cells=table.select('tr:first-child > td')
        if len(cells)!=2 or cells[0].get_text(strip=True)!='場地名稱':
            continue
        name=cells[1].get_text(' ',strip=True)
        photos=[]
        for link in gallery.select('a.cboxElement[href]'):
            url=urljoin(source_url,link['href'])
            if allowed_photo(url) and not any(p['url']==url for p in photos):
                photos.append({'url':url,'source_url':source_url,'credit':'康樂及文化事務署','alt':name+'・場地實景'})
        if photos:
            result[name_key(name)]=photos[:2]
    return result


def attach_photos(places, path=MANIFEST):
    # Explicit IDs keep images from similarly named branches from crossing over.
    try:
        manifest=json.loads(path.read_text())['places']
    except (OSError, ValueError, KeyError, TypeError):
        manifest={}
    from backend.app.models.pet import PlacePhoto
    for place in places:
        if place.category=='restaurants':
            continue
        records=manifest.get(place.id)
        if records is not None:
            try:
                place.photos=[PlacePhoto.model_validate(p) for p in records[:2]]
            except (ValueError,TypeError):
                place.photos=[]

    from backend.app.data.google_facility_photos import attach_google_facility_photos
    attach_google_facility_photos(places)
