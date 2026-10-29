import {getPlaceDetails} from '../../api/client';
import { useEffect, useRef, useState } from 'react';
import { Circle, CircleMarker, Marker, MapContainer, Popup, Tooltip, ZoomControl, useMap, useMapEvents } from 'react-leaflet';
import { divIcon, latLngBounds, type CircleMarker as LeafletCircleMarker, type Marker as LeafletMarker, type Popup as LeafletPopup } from 'leaflet';
import { renderToStaticMarkup } from 'react-dom/server';
import Icon from '../../components/Icon';
import { facilityVisual } from '../../components/facility-categories';
import { maplibreGL } from '@maplibre/maplibre-gl-leaflet';
import { setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { setBasemapLanguage, simplifyBasemap } from './basemap-style';
import { useLanguage,hasChinese } from '../../language';
import MallPolicyDetails from '../../components/MallPolicy';
import RestaurantPopup from '../../components/RestaurantPopup';
import {FacilityGallery} from '../../components/FacilityPhotos';
import { navigationUrl, safeExternal } from './venue-links';
import type { PetPlace } from '../../api/client';
import type { ParkingGroup } from '../../api/plans';
import { restaurantColor } from './cuisine-colors';
import {getPetAmenities, petAmenities} from './pet-amenities';
import {clusterPlaces} from './map-clusters';
setWorkerUrl(workerUrl);
const FACILITY_ICON_ZOOM = 15;
export const colors: Record<string,string> = {restaurants:'#db6339', parks:'#70866d', pet_parks:'#286b47', inclusive_parks:'#70866d', vets:'#3976a5', hotels:'#8b5ba8', management:'#317f83', malls:'#ba527f',parking:'#365c69'};
export const labels: Record<string,string> = {restaurants:'狗友善餐廳',parks:'一般公園',pet_parks:'寵物公園',inclusive_parks:'一般公園',vets:'獸醫診所／動物醫院',hotels:'持牌寵物寄養所',management:'動物管理／注射中心',malls:'寵物友善商場',parking:'停車場'};
function MinimalBasemap() {
  const map = useMap();
  const { language } = useLanguage();
  const languageRef = useRef(language);
  const vectorRef = useRef<ReturnType<ReturnType<typeof maplibreGL>['getMaplibreMap']> | null>(null);
  languageRef.current = language;

  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({pan: false}));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);

  useEffect(() => {
    const layer = maplibreGL({
      style: 'https://tiles.openfreemap.org/styles/positron',
      attributionControl: { customAttribution:
        '<a href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a> · ' +
        '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener noreferrer">© OpenMapTiles</a> · ' +
        '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a>',
      },
    }).addTo(map);

    const vectorMap = layer.getMaplibreMap();
    vectorRef.current = vectorMap;
    vectorMap.on('style.load', () => simplifyBasemap(vectorMap, languageRef.current));

    return () => { vectorRef.current = null; map.removeLayer(layer); };
  }, [map]);

  useEffect(() => {
    const vectorMap = vectorRef.current;
    if (vectorMap?.isStyleLoaded()) setBasemapLanguage(vectorMap, language);
  }, [language]);

  return null;
}

function LocateButton() {
  const map = useMap();
  const { tx } = useLanguage();
  const [position, setPosition] = useState<[number, number] | null>(null);
  const [notice, setNotice] = useState('');
  const [locating, setLocating] = useState(false);

  function locate() {
    if (!navigator.geolocation) { setNotice('瀏覽器唔支援定位，你可以拖動地圖揀地區。'); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      const point: [number, number] = [coords.latitude, coords.longitude];
      setPosition(point);
      map.flyTo(point, 15);
      setNotice('搵到你嘅位置，只會喺今次頁面使用。');
      setLocating(false);
    }, () => {
      setNotice('暫時定位唔到，你仍然可以拖動地圖揀地區。');
      setLocating(false);
    }, { enableHighAccuracy: false, timeout: 10000 });
  }
  return <>
    <div className="location-control"><button disabled={locating} onClick={locate}><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3.5M12 18.5V22M2 12h3.5M18.5 12H22"/></svg>{locating ? tx('定位緊…') : tx('定位到我')}</button>{notice && <p role="status">{tx(notice)}</p>}</div>
    {position && <CircleMarker center={position} radius={7}><Popup>{tx('你嘅位置')}</Popup></CircleMarker>}
  </>;
}

function MapView({viewKey}: {viewKey: string}) {
  const map = useMap();
  useEffect(() => {
    map.closePopup();
    map.setView([22.3193, 114.1694], 11, {animate: false});
  }, [map, viewKey]);
  return null;
}

function VenueDetails({place,enabled}:{place:PetPlace;enabled:boolean}) {
  const {language,tx,placeName,placeAddress,localText,sourceName,category}=useLanguage();
  const [loaded,setLoaded]=useState<{source:PetPlace;value:PetPlace}|null>(null);
  const [error,setError]=useState(false);
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    if(!enabled||place.detail_loaded!==false)return;
    const controller=new AbortController();setError(false);
    getPlaceDetails(place.id,controller.signal).then(value=>setLoaded({source:place,value}))
      .catch(()=>{if(!controller.signal.aborted)setError(true);});
    return()=>controller.abort();
  },[enabled,place,attempt]);
  const p=place.detail_loaded!==false?place:loaded?.source===place?loaded.value:null;
  if(!p)return error?<button onClick={()=>setAttempt(n=>n+1)}>{language==='en'?'Unable to load details. Retry':'暫時讀唔到詳情，重試'}</button>:<p role="status">{tx('讀緊資料，等一等…')}</p>;
  if(p.category==='restaurants')return <RestaurantPopup place={p}/>;
  return <section>
      <span className="pet-kicker">{category(p.category)}</span><h3>{placeName(p)}</h3>{language==='zh-Hant' && p.name_en && p.name_en!==p.name && <small>{p.name_en}</small>}{language==='en' && !p.name_en && hasChinese(p.name) && <small>{tx('名稱只提供中文')}</small>}
      <MallPolicyDetails place={p}/><FacilityGallery place={p}/>
      {p.category!=='restaurants' && <div className="pet-amenity-tags">{petAmenities.filter(item=>getPetAmenities(p).includes(item.key)).map(item=><span key={item.key}>{tx(item.label)}</span>)}</div>}
      <p>{placeAddress(p)} <a href={navigationUrl(p)} target="_blank" rel="noopener noreferrer">{tx("導航 ↗")}</a></p>
      {p.category==='restaurants' && <p>{tx("食物種類：")}{(p.cuisines.length?p.cuisines:['未分類']).map(c=>tx(c)).join(' / ')} {safeExternal(p.cuisine_source) && <a href={safeExternal(p.cuisine_source)} target="_blank" rel="noopener noreferrer">{tx("分類來源 ↗")}</a>}</p>}
      {p.telephone && <p>{tx("電話：")}<a href={`tel:${p.telephone.replace(/[^+0-9]/g,'')}`}>{p.telephone}</a></p>}
      {(p.opening_hours || p.opening_hours_en) && <p>{tx("開放時間：")}{localText(p.opening_hours,p.opening_hours_en)}</p>}
      {p.licence_number && <p>{tx("牌照號碼：")}{p.licence_number}</p>}
      {(language==='en'?(p.notes_en || []):p.notes).map(n=><p className="pet-note" key={n}>{n}</p>)}
      {language==='en' && p.notes.length>0 && <details><summary>{tx('中文原文')}</summary>{p.notes.map(n=><p key={n}>{n}</p>)}</details>}
      {language==='en' && p.address && !p.address_en && hasChinese(p.address) && <small>{tx('地址只提供中文')}</small>}
      {safeExternal(language==='en'?(p.rules_url_en||p.rules_url):p.rules_url) && <p><a href={safeExternal(language==='en'?(p.rules_url_en||p.rules_url):p.rules_url)} target="_blank" rel="noopener noreferrer">{tx("餐廳攜狗守則 ↗")}</a></p>}
      {safeExternal(language==='en'?(p.website_en||p.website):p.website) && <p><a href={safeExternal(language==='en'?(p.website_en||p.website):p.website)} target="_blank" rel="noopener noreferrer">{tx("場地網站 ↗")}</a></p>}
      <p><a href={safeExternal(p.source_url)} target="_blank" rel="noopener noreferrer">{tx("資料來源：")}{sourceName(p.source_name,p.source_name_en)} ↗</a></p>
      <small>{tx("地圖標記係場地代表點，唔一定係入口。導航路線唔保證可以攜寵。")}</small>
    </section>;
}

function PlaceMarker({place, related, active, offset=[0,0]}: {place: PetPlace; related: PetPlace[]; active: PetPlace|null; offset?: [number,number]}) {
  const {language,tx,placeName,placeAddress,localText,sourceName,category}=useLanguage();
  const map=useMap();
  const [zoom,setZoom]=useState(map.getZoom());
  const [popupOpen,setPopupOpen]=useState(false);
  useMapEvents({zoomend:()=>setZoom(map.getZoom())});
  const popupRef=useRef<LeafletPopup>(null);
  useEffect(()=>{
    if(!popupOpen)return;
    const popup=popupRef.current;
    const element=popup?.getElement()?.querySelector('.leaflet-popup-content');
    if(!popup||!element)return;
    let frame=0;
    const observer=new ResizeObserver(()=>{
      cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>popup.update());
    });
    observer.observe(element);
    const moved=()=>popup.isOpen()&&popup.update();
    map.on('moveend',moved);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);map.off('moveend',moved);};
  },[popupOpen,map]);
  const ref=useRef<LeafletCircleMarker>(null);
  const facilityRef=useRef<LeafletMarker>(null);
  useEffect(()=>{if(active && place.latitude !== null && place.longitude !== null){const target:[number,number]=[place.latitude,place.longitude];if(map.getZoom()<15||!map.getBounds().contains(target))map.flyTo(target,16,{duration:.5});(ref.current||facilityRef.current)?.openPopup();}},[active,map,place.id]);
  useEffect(()=>{if(!active)return;const timer=window.setTimeout(()=>{(facilityRef.current||ref.current)?.openPopup();},80);return()=>window.clearTimeout(timer);},[active,place.id,zoom>=FACILITY_ICON_ZOOM]);
  if(place.latitude===null || place.longitude===null)return null;
  const point=map.project([place.latitude,place.longitude],zoom);
  const showFacilityIcon=zoom>=FACILITY_ICON_ZOOM;
  const offsetScale=place.category==='restaurants'||showFacilityIcon?1:12/22;
  const center=map.unproject([point.x+offset[0]*offsetScale,point.y+offset[1]*offsetScale],zoom);
  const content=<>
    <Tooltip>{placeName(place)}{place.category==='restaurants' && ` · ${(place.cuisines.length?place.cuisines:['未分類']).map(c=>tx(c)).join(' / ')}`}</Tooltip>
    <Popup ref={popupRef} eventHandlers={{add:()=>setPopupOpen(true),remove:()=>setPopupOpen(false)}} maxWidth={400} className={place.category==='restaurants'?'restaurant-popup-shell':''}><div className={place.category==='restaurants'?'venue-popup restaurant-popup-wrap':'venue-popup'}>{related.map(p=><VenueDetails key={p.id} place={p} enabled={popupOpen}/>)}</div></Popup>
  </>;
  if(place.category==='restaurants'){
    const rating=place.restaurant_details?.rating;
    const ratingIcon=divIcon({className:'facility-map-icon',
      html:renderToStaticMarkup(<span className={`restaurant-rating-pin${active?' is-active':''}`} style={{background:restaurantColor(place)}}><span aria-hidden="true">★</span>{rating!=null?rating.toFixed(1):'–'}</span>),
      iconSize:[48,26],iconAnchor:[24,13],popupAnchor:[0,-14],tooltipAnchor:[24,0]});
    const dotSize=active?20:12;
    const dotIcon=divIcon({className:'facility-map-icon',html:renderToStaticMarkup(<span style={{display:'block',width:dotSize,height:dotSize,boxSizing:'border-box',border:'2px solid white',borderRadius:'50%',background:restaurantColor(place)}}/>),iconSize:[dotSize,dotSize],iconAnchor:[dotSize/2,dotSize/2]});
    return <Marker ref={facilityRef} position={center} icon={showFacilityIcon?ratingIcon:dotIcon} title={placeName(place)} alt={placeName(place)} zIndexOffset={active?500:0}>{content}</Marker>;
  }
  const visual=facilityVisual(place.category);
  const markerSize=showFacilityIcon?32:active?20:12;
  const markerIcon=divIcon({className:'facility-map-icon',
    html:renderToStaticMarkup(<span className={`${showFacilityIcon?'facility-map-pin':'facility-map-dot'}${active?' is-active':''}`} style={{color:visual.color}}>{showFacilityIcon && <Icon name={visual.icon} size={21}/>}</span>),
    iconSize:[markerSize,markerSize],iconAnchor:[markerSize/2,markerSize/2],popupAnchor:[0,-markerSize/2-1],tooltipAnchor:[markerSize/2,0]});
  return <Marker ref={facilityRef} position={center} icon={markerIcon} title={placeName(place)} alt={placeName(place)} zIndexOffset={active?500:0}>{content}</Marker>;
}
function ParkingCoverage({groups,viewKey}: {groups: ParkingGroup[];viewKey:string}) {
  const map = useMap();
  const {language} = useLanguage();
  const signature=groups.map(g=>`${g.parking.id}:${g.parking.latitude}:${g.parking.longitude}`).join('|');
  useEffect(()=>{
    if (!groups.length) return;
    const bounds=latLngBounds([]);
    for(const group of groups){
      const p=group.parking, delta=(group.radius_m||1000)/111320;
      const lonDelta=delta/Math.cos(p.latitude*Math.PI/180);
      bounds.extend([p.latitude-delta,p.longitude-lonDelta]);
      bounds.extend([p.latitude+delta,p.longitude+lonDelta]);
    }
    const fit = () => {
      const mobile=window.innerWidth<800;
      const bottom=mobile?Math.min(window.innerHeight*.46,map.getSize().y*.6)+30:35;
      map.fitBounds(bounds,{paddingTopLeft:[30,25],paddingBottomRight:[30,bottom],maxZoom:15});
    };
    fit();
    let resizeTimer: number;
    const resize = () => { window.clearTimeout(resizeTimer); resizeTimer=window.setTimeout(fit,100); };
    map.on('resize',resize);
    window.addEventListener('resize',resize);
    return ()=>{map.off('resize',resize);window.removeEventListener('resize',resize);window.clearTimeout(resizeTimer);};
  },[map,signature,viewKey]);
  return <>{groups.map((group,index)=>{
    const p=group.parking, name=language==='en'?(p.name_en||p.name):p.name;
    const url=safeExternal(p.navigation_url)||`https://www.google.com/maps/dir/?api=1&destination=${p.latitude},${p.longitude}&travelmode=driving`;
    return <Circle key={p.id+index} center={[p.latitude,p.longitude]} radius={group.radius_m||1000} pathOptions={{color:'#557b85',weight:1.5,dashArray:'6 6',fillColor:'#7c9c85',fillOpacity:.065}}>
      <Tooltip sticky>{language==='en'?'1 km around parking':'停車場周邊一公里'}</Tooltip>
      <Marker position={[p.latitude,p.longitude]} zIndexOffset={700} icon={divIcon({className:'facility-map-icon',html:`<span class="parking-map-pin">P${index+1}</span>`,iconSize:[35,29],iconAnchor:[17,14]})} title={name} alt={name}>
        <Tooltip>{name}</Tooltip><Popup><div className="parking-popup"><span className="pet-kicker">{language==='en'?'PARK & EXPLORE':'停車出遊'}</span><h3>{name}</h3>
          <p>{language==='en'?(p.address_en||p.address):p.address}</p>{p.fee_summary&&<p>{p.fee_summary}</p>}
          <p>{p.stale||p.vacancy_status==='stale'?(language==='en'?'Vacancy data is out of date':'空位資料已過期'):p.vacancy!=null?`${p.vacancy} ${language==='en'?'spaces reported':'個空位'}`:(language==='en'?'Vacancy not available':'未有空位資料')}</p>
          <a href={url} target="_blank" rel="noopener noreferrer">{language==='en'?'Drive to this car park ↗':'導航去呢個停車場 ↗'}</a>
        </div></Popup>
      </Marker>
    </Circle>;
  })}</>;
}

function VisiblePlaces({places,activePlace,cluster=true}:{places:PetPlace[];activePlace:PetPlace|null;cluster?:boolean}) {
  const map=useMap();
  const {language}=useLanguage();
  const [,setView]=useState(0);
  useMapEvents({moveend:()=>setView(n=>n+1),resize:()=>setView(n=>n+1)});
  const bounds=map.getBounds().pad(.2);
  const {individuals,clusters}=clusterPlaces(places,map.getZoom(),(lat,lon)=>bounds.contains([lat,lon]),activePlace?.id,cluster);
  const groups=new Map<string,PetPlace[]>();
  for(const p of individuals){if(p.latitude===null || p.longitude===null)continue;const key=`${p.latitude.toFixed(5)},${p.longitude.toFixed(5)}`;groups.set(key,[...(groups.get(key)||[]),p]);}
  return <>
    {clusters.map(c=><Marker key={`cluster:${c.key}`} position={[c.latitude,c.longitude]}
      icon={divIcon({className:'facility-map-icon',html:`<span style="display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:#286b47;color:white;border:3px solid white;box-shadow:0 1px 5px #0004;font-weight:700">${c.count}</span>`,iconSize:[38,38],iconAnchor:[19,19]})}
      title={`${c.count} ${language==='en'?'places — zoom in':'個地點，點擊放大'}`}
      eventHandlers={{click:()=>map.flyTo([c.latitude,c.longitude],Math.min(16,map.getZoom()+2),{duration:.4})}}/>) }
    {[...groups.entries()].flatMap(([key,group])=>{
      const buckets=new Map<string,PetPlace[]>();
      for(const p of group){const type=p.category==='restaurants'?(p.cuisines[0]||'未分類'):p.category;buckets.set(type,[...(buckets.get(type)||[]),p]);}
      return [...buckets.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([type,related],i)=>{
        const angle=2*Math.PI*i/buckets.size;
        const spread=related[0].category==='restaurants'?12:22;
        const offset: [number,number]=buckets.size>1?[Math.cos(angle)*spread,Math.sin(angle)*spread]:[0,0];
        return <PlaceMarker key={`${key}:${type}`} place={related.find(p=>p.id===activePlace?.id)||related[0]} related={related} offset={offset} active={related.some(p=>p.id===activePlace?.id)?activePlace:null}/>;
      });
    })}
  </>;
}

export default function VenueMap({places,activePlace,viewKey,parkingGroups=[]}: {places:PetPlace[];activePlace:PetPlace|null;viewKey:string;parkingGroups?:ParkingGroup[]}) {
  return <MapContainer center={[22.3193,114.1694]} zoom={11} zoomControl={false} scrollWheelZoom className="venue-map">
    <MinimalBasemap/><MapView viewKey={viewKey}/><ParkingCoverage groups={parkingGroups} viewKey={viewKey}/><ZoomControl position="topright"/><LocateButton/>
    <VisiblePlaces places={places} activePlace={activePlace} cluster={!viewKey.startsWith('plan:')}/>
  </MapContainer>;
}
