import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { getActivities, getCatalog, getPlaces, getDataVersion, getParking, type ActivityCollection, type Catalog, type PetActivity, type PetPlace, type PlaceCollection } from './api/client';
import Icon from './components/Icon';
import {getPetAmenities, type PetAmenity} from './features/map/pet-amenities';
import PlaceCard from './components/PlaceCard';
import PetIllustration from './components/PetIllustration';
import VenueMap from './features/map/VenueMap';
import {cuisineColor} from './features/map/cuisine-colors';
import {navigationUrl, safeExternal} from './features/map/venue-links';
const AssistantPanel = lazy(() => import('./features/assistant/AssistantPanel'));
import { LanguageProvider, useLanguage } from './language';
import ExploreCategories, {groupedCategory} from './features/explore/ExploreCategories';
import PlanPanel from './features/plan/PlanPanel';
import type {TripPlan} from './api/plans';
import './pet.css';

type Mode = 'restaurants' | 'plan' | 'explore';

function AppContent() {
  const {language,setLanguage,tx,errorText,localText,placeName,placeAddress,activityName,activityDates,districtName,sourceName,formatTime:updated,count}=useLanguage();
  const [mode,setMode]=useState<Mode>('restaurants');
  const [exploreSection,setExploreSection]=useState<'places'|'activities'>('places');
  const isActivities=mode==='explore' && exploreSection==='activities';
  const isExplorePlaces=mode==='explore' && exploreSection==='places';
  const [tripPlan,setTripPlan]=useState<TripPlan|null>(null);
  const [parkingPlaces,setParkingPlaces]=useState<PetPlace[]>([]);
  const [activitiesPending,setActivitiesPending]=useState(false);
  const activityRequest=useRef<AbortController|null>(null);
  const [panel,setPanel]=useState<'index'|'search'|null>(()=>window.innerWidth>=900?'index':null);
  const [catalog,setCatalog]=useState<Catalog|null>(null);
  const [places,setPlaces]=useState<PlaceCollection|null>(null);
  const [activities,setActivities]=useState<ActivityCollection|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  const [activePlace,setActivePlace]=useState<PetPlace|null>(null);
  const [activeActivity,setActiveActivity]=useState<PetActivity|null>(null);
  const [assistantOpen,setAssistantOpen]=useState(false);
  const [pendingPlaceId,setPendingPlaceId]=useState<string|null>(null);
  const [query,setQuery]=useState('');
  const [district,setDistrict]=useState('');
  const [categories,setCategories]=useState<string[]|null>(null);
  const [cuisines,setCuisines]=useState<string[]|null>(null);
  const [activityCategory,setActivityCategory]=useState('');
  const [selectedAmenities,setSelectedAmenities]=useState<PetAmenity[]>([]);
  const [visibleCount,setVisibleCount]=useState(40);
  const searchRef=useRef<HTMLInputElement>(null);
  const indexRef=useRef<HTMLButtonElement>(null);

  useEffect(()=>{
    const controller=new AbortController();
    let busy=false,knownVersion='',lastCheck=0;
    async function load(force=false){
      if(busy||document.hidden)return;
      busy=true;lastCheck=Date.now();
      try{
        const version=await getDataVersion(controller.signal);
        if(!force&&version.revision===knownVersion)return;
        const [c,p]=await Promise.all([getCatalog(controller.signal,version.revision),getPlaces(controller.signal)]);
        if(controller.signal.aborted)return;
        setCatalog(c);setPlaces(p);setError('');
        knownVersion=p.revision||version.revision;
      }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'暫時連唔到資料服務。');}
      finally{busy=false;if(!controller.signal.aborted)setLoading(false);}
    }
    void load(true);
    const timer=window.setInterval(()=>void load(),300000);
    const visible=()=>{if(!document.hidden&&Date.now()-lastCheck>=300000)void load();};
    document.addEventListener('visibilitychange',visible);
    return()=>{controller.abort();window.clearInterval(timer);document.removeEventListener('visibilitychange',visible);};
  },[revision]);
  useEffect(()=>()=>activityRequest.current?.abort(),[]);
  useEffect(()=>{
    if(mode!=='explore')return;
    const controller=new AbortController();
    getParking(controller.signal,language).then(data=>setParkingPlaces(data.items)).catch(()=>{});
    return()=>controller.abort();
  },[mode,language]);
  async function refreshActivities(){
    activityRequest.current?.abort();
    const controller=new AbortController();activityRequest.current=controller;setActivitiesPending(true);
    try{const data=await getActivities(controller.signal);if(!controller.signal.aborted){setActivities(data);setError('');}}
    catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'暫時連唔到資料服務。');}
    finally{if(!controller.signal.aborted)setActivitiesPending(false);}
  }
  useEffect(()=>{if(panel==='search')searchRef.current?.focus();},[panel]);
  useEffect(()=>{setVisibleCount(40);setActiveActivity(null);setActivePlace(null);},[mode,exploreSection,query,district,categories,cuisines,activityCategory,selectedAmenities]);
  useEffect(()=>{
    const handler=(e:KeyboardEvent)=>{if(e.key==='Escape' && !assistantOpen){setPanel(null);setActiveActivity(null);indexRef.current?.focus();}};
    window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);
  },[assistantOpen]);
  const allPlaces=useMemo(()=>[...(places?.items || []),...parkingPlaces].filter(p=>p.category!=='transport'),[places,parkingPlaces]);
  const allCuisines=catalog?.cuisines || ['未分類'];
  const modePlaces=allPlaces.filter(p=>mode==='restaurants'?p.category==='restaurants':p.category!=='restaurants');
  const districts=Array.from(new Set((isActivities?(activities?.items || []).map(a=>a.district):modePlaces.map(p=>p.district)).filter((v):v is string=>Boolean(v)))).sort((a,b)=>districtName(a).localeCompare(districtName(b),language==='en'?'en':'zh-HK'));
  const baseFilteredPlaces=useMemo(()=>allPlaces.filter(p=>{
    if(mode==='restaurants' && p.category!=='restaurants')return false;
    if(isExplorePlaces && p.category==='restaurants')return false;
    if(isExplorePlaces && categories!==null && !categories.includes(groupedCategory(p.category)))return false;
    if(mode==='restaurants' && cuisines!==null && !(p.cuisines.length?p.cuisines:['未分類']).some(c=>cuisines.includes(c)))return false;
    if(district && p.district?.replace(/區$/,'')!==district.replace(/區$/,''))return false;
    return !query || `${p.restaurant_details?.display_name||''} ${p.name} ${p.name_en||''} ${p.address||''} ${p.address_en||''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase());
  }),[allPlaces,mode,exploreSection,categories,cuisines,district,query]);
  const filteredPlaces=useMemo(()=>isExplorePlaces && selectedAmenities.length
    ?baseFilteredPlaces.filter(p=>p.category==='pet_parks'&&selectedAmenities.every(key=>getPetAmenities(p).includes(key)))
    :baseFilteredPlaces,[baseFilteredPlaces,mode,selectedAmenities]);
  const filteredActivities=(activities?.items || []).filter(a=>(!activityCategory||a.category===activityCategory)&&(!district||a.district?.replace(/區$/,'')===district.replace(/區$/,''))&&(!query||`${a.name} ${a.name_en||''} ${a.venue_name||''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())));
  const activityPlaces=allPlaces.filter(p=>filteredActivities.some(a=>a.place_id===p.id));
  const planParkingIds=new Set(tripPlan?.parking_groups.map(group=>group.parking.id)||[]);
  const mapPlaces=mode==='plan'?(tripPlan?.map_places.filter(place=>!planParkingIds.has(place.id)) || allPlaces.filter(p=>p.category!=='restaurants')):isActivities?activityPlaces:filteredPlaces;
  const mapped=mapPlaces.filter(p=>p.latitude!==null && p.longitude!==null);
  const total=mode==='plan'?mapPlaces.length:isActivities?filteredActivities.length:filteredPlaces.length;
  useEffect(()=>{
    if(!pendingPlaceId)return;
    const target=filteredPlaces.find(p=>p.id===pendingPlaceId);
    if(target){setActivePlace(target);setPendingPlaceId(null);}
  },[pendingPlaceId,filteredPlaces]);
  function changeMode(next:Mode){setMode(next);setActivePlace(null);setActiveActivity(null);setQuery('');setDistrict('');setPanel('index');}
  function toggle(value:string, selected:string[]|null, all:string[], apply:(next:string[]|null)=>void){
    const current=selected || all;const next=current.includes(value)?current.filter(c=>c!==value):[...current,value];
    apply(next.length===all.length?null:next);
  }
  function showPlaceFromAssistant(id:string){
    const target=allPlaces.find(p=>p.id===id);
    if(!target)return;
    setMode(target.category==='restaurants'?'restaurants':'explore');setExploreSection('places');
    setQuery('');setDistrict('');setCategories(null);setCuisines(null);setSelectedAmenities([]);setPanel(null);
    setPendingPlaceId(id);
  }
  function selectPlace(p:PetPlace){setActivePlace({...p});if(window.innerWidth<800)setPanel(null);}
  const relevantSources=(catalog?.sources || []).filter(s=>mode==='restaurants'?s.key==='restaurants':isActivities?(s.key==='activities'||s.key.startsWith('activities_')):s.key!=='restaurants'&&!s.key.startsWith('activities'));
  const sourceProblem=relevantSources.some(s=>s.status!=='ready');
  const snapshotOld=(isActivities?activities?.status:places?.status)==='stale';

  const filterCount=(district?1:0)+(query?1:0)+(mode==='restaurants' && cuisines!==null?1:0)+(isExplorePlaces && categories!==null?1:0)+(isExplorePlaces?selectedAmenities.length:0)+(isActivities && activityCategory?1:0);

  return <main className={`map-app pet-app${panel!==null?' has-panel':''}`}>
    <header className="topbar">
      <div className="topbar-start">
        <button ref={indexRef} className={`index-toggle ${panel==='index'?'is-active':''}`} aria-label={tx("開啟分類索引")} aria-expanded={panel==='index'} aria-controls="pet-sidebar" onClick={()=>setPanel(panel==='index'?null:'index')}><Icon name="menu" size={22}/><span>{tx("索引")}</span></button>
        <span className="topbar-divider"/>
        <a className="brand" href={`/?lang=${language}`} aria-label={`HK Pet Map · ${tx("香港寵物地圖")}`}><span className="brand-mark"><Icon name="paw" size={27}/></span><span>HK Pet Map<small>{tx("香港寵物地圖")}</small></span></a>
      </div>
      <nav className="pet-tabs" aria-label={tx("地圖類別")}>{([['restaurants',tx("餐廳")],['plan',tx("行程")],['explore',tx("探索")]] as const).map(([key,label])=><button key={key} aria-pressed={mode===key} className={mode===key?'active':''} onClick={()=>changeMode(key)}><Icon name={key==='restaurants'?'dining':key==='plan'?'trail':'pet-park'} size={18}/>{label}</button>)}</nav>
      <div className="pet-header-tools"><div className="pet-top-status"><span className="status-dot"/>{loading?tx("讀緊資料…"):count(total,isActivities?'activities':'places')}</div><div className="language-switch" role="group" aria-label={tx("語言")}><button type="button" aria-pressed={language==='zh-Hant'} onClick={()=>setLanguage('zh-Hant')}>{tx("粵語")}</button><button type="button" aria-pressed={language==='en'} onClick={()=>setLanguage('en')}>EN</button></div></div>
    </header>
    <div className="map-panel"><VenueMap viewKey={mode==='plan' && tripPlan?`plan:${tripPlan.id}`:mode} places={mapPlaces} activePlace={activePlace} parkingGroups={mode==='plan'?tripPlan?.parking_groups:undefined} onDismiss={id=>setActivePlace(current=>current?.id===id?null:current)}/></div>
    <div className="pet-map-source"><span>Source:</span><a href="https://github.com/sammyliao1146-ship-it/hkpetmap.git" target="_blank" rel="noopener noreferrer">https://github.com/sammyliao1146-ship-it/hkpetmap.git</a></div>
    <div className="pet-search-dock" hidden={panel!==null||mode==='plan'}>
      <div className="pet-dock-welcome"><div><span className="eyebrow">{tx('同毛孩一齊出發')}</span><h1>{tx('今日，去邊好？')}</h1><p>{tx('每一步，都有毛孩陪住。')}</p></div><PetIllustration/></div>
      <button className="search-entry" onClick={()=>setPanel('search')}><Icon name="search"/><span>{mode==='restaurants'?tx("搵餐廳、地址…"):isActivities?tx("搵課程、活動…"):tx("搵公園、獸醫、酒店…")}</span><span className="pet-search-key">{tx("搜尋")}</span></button>
      <div className="pet-map-summary">{isActivities?tx("課程地點"):mode==='restaurants'?tx("狗友善餐廳"):tx("寵物設施")}・{count(mapped.length,'markers')}<button onClick={()=>setPanel('index')}>{tx("篩選 ↗")}</button></div>
    </div>
    <div className="pet-map-label"><Icon name="paw" size={16}/><span>{tx("香港寵物地圖")}</span><i/>{count(mapped.length,'markers')}</div>
    {mode==='restaurants' && <details className="cuisine-legend"><summary>{tx('菜系圖例')}</summary><div>{allCuisines.filter(c=>filteredPlaces.some(p=>(p.cuisines.length?p.cuisines:['未分類']).includes(c))).map(c=><button key={c} type="button" onClick={()=>setCuisines(cuisines?.length===1 && cuisines[0]===c?null:[c])}><i className="cuisine-swatch" style={{background:cuisineColor(c)}} aria-hidden="true"/>{tx(c)}</button>)}</div><button type="button" className="legend-reset" onClick={()=>setCuisines(null)}>{tx('全部種類')}</button></details>}
    <div hidden={mode!=='plan'} className="plan-view"><PlanPanel cuisineOptions={allCuisines} onPlanChange={plan=>{setTripPlan(plan);setActivePlace(null);}} onSelectPlace={selectPlace}/></div>
    {panel!==null && mode!=='plan' && <aside id="pet-sidebar" className="pet-sidebar" aria-label={panel==='search'?tx("搜尋地點"):tx("分類索引")}>
      <div className="panel-heading"><div className="pet-heading-copy"><span className="eyebrow"><Icon name="paw" size={12}/>{tx("同毛孩一齊出發")}</span><h1>{panel==='search'?tx("搵個好去處"):mode==='restaurants'?tx("食啲乜好？"):tx("探索設施同活動")}</h1><p>{mode==='restaurants'?tx("好好食飯，毛孩都有份。"):isExplorePlaces?tx("散步、玩樂、照顧，一張地圖搵齊。"):tx("一齊學新嘢，儲多啲開心回憶。")}</p></div><PetIllustration/><button className="icon-button" aria-label={tx("收起側欄")} onClick={()=>{setPanel(null);indexRef.current?.focus();}}><Icon name="close"/></button></div>
      <div className="pet-search-row"><Icon name="search" size={18}/><input ref={searchRef} aria-label={tx("搜尋名稱或地址")} placeholder={isActivities?tx("課程名、活動名…"):tx("名稱、地址…")} value={query} onChange={e=>setQuery(e.target.value)}/>{query && <button aria-label={tx("清除搜尋")} onClick={()=>setQuery('')}>×</button>}</div>
      <div className="pet-scroll">
        <label className="pet-district">{tx("地區")}<select value={district} onChange={e=>setDistrict(e.target.value)}><option value="">{tx("全部地區")}</option>{districts.map(d=><option key={d} value={d}>{districtName(d)}</option>)}</select></label>
        {panel==='index' && <details className="pet-filter-drawer" key={mode} open><summary><span><Icon name="layers" size={17}/>{tx('分類')}{filterCount>0 && <b>{filterCount}</b>}</span><Icon name="chevron" size={16}/></summary><div className="pet-filter-body">
        {panel==='index' && mode==='restaurants' && <section className="pet-filters"><div className="pet-section-heading"><h2>{tx("食物種類")}</h2><button onClick={()=>setCuisines(null)}>{tx("重設")}</button></div>
          <label className="pet-checkbox"><input type="checkbox" checked={cuisines===null} onChange={e=>setCuisines(e.target.checked?null:[])}/><span>{tx("全部種類")}</span><em>{modePlaces.length}</em></label>
          <div className="pet-cuisine-grid">{allCuisines.map(c=><label key={c} className="pet-cuisine"><input type="checkbox" checked={cuisines===null||cuisines.includes(c)} onChange={()=>toggle(c,cuisines,allCuisines,setCuisines)}/><i className="cuisine-swatch" style={{background:cuisineColor(c)}} aria-hidden="true"/><span>{tx(c)}</span><em>{modePlaces.filter(p=>(p.cuisines.length?p.cuisines:['未分類']).includes(c)).length}</em></label>)}</div>
          <p className="muted">{tx("菜系綜合已核實品牌資料同本地 Google 分類；未能可靠配對嘅餐廳保留「未分類」。圓點顏色以第一項菜系為準。")}</p>
        </section>}
        {mode==='explore' && <div className="explore-branches"><button type="button" className={isExplorePlaces?'active':''} aria-pressed={isExplorePlaces} onClick={()=>setExploreSection('places')}><Icon name="layers" size={15}/>{tx('設施')}</button><button type="button" className={isActivities?'active':''} aria-pressed={isActivities} onClick={()=>{setExploreSection('activities');void refreshActivities();}}><Icon name="calendar" size={15}/>{tx('活動')}</button></div>}
        {panel==='index' && isExplorePlaces && <ExploreCategories places={modePlaces} categories={categories} selectedAmenities={selectedAmenities} onCategoriesChange={setCategories} onAmenitiesChange={setSelectedAmenities}/>}
        {isActivities && <section className="pet-filters"><div className="explore-activity-heading"><h2>{tx('活動種類')}</h2><button className="explore-activity-refresh" type="button" disabled={activitiesPending} onClick={()=>void refreshActivities()}>{tx(activitiesPending?'更新活動中…':'更新活動')}</button></div><label className="pet-district">{tx("活動種類")}<select value={activityCategory} onChange={e=>{setActivityCategory(e.target.value);void refreshActivities();}}><option value="">{tx("全部活動")}</option>{Array.from(new Set((activities?.items||[]).map(a=>a.category))).map(c=><option key={c} value={c}>{tx(c)}</option>)}</select></label><p className="muted">{tx("公開活動資料・實際安排同名額以主辦方為準")}</p><p className="muted">{tx('點擊活動目錄或更新按鈕時讀取最新資料。')}</p></section>}
        </div></details>}
        {error && <p className="inline-error" role="alert">{errorText(error)}<button onClick={()=>setRevision(n=>n+1)}>{tx("再試")}</button></p>}
        <div className="pet-section-heading"><h2>{isActivities?tx("公開課程同活動"):tx("地點列表")}</h2><span>{count(total,'results')}</span></div>
        {(loading||activitiesPending) && <p className="pet-empty" role="status">{tx("讀緊資料，等一等…")}</p>}
        {!loading && !activitiesPending && total===0 && <div className="pet-empty"><Icon name="search" size={28}/><p>{places?.status==='not_synced'?tx("暫未有資料快照，請先執行同步任務。"):tx("呢個篩選暫時未有結果，試吓其他地區或分類。")}</p><small>{tx("未有記錄唔代表已滿，亦唔代表冇呢類場地。")}</small></div>}
        {!isActivities && filteredPlaces.slice(0,visibleCount).map(p=><PlaceCard key={p.id} place={p} selected={activePlace?.id===p.id} onSelect={()=>selectPlace(p)}/>)}
        {isActivities && filteredActivities.slice(0,visibleCount).map(a=><button className="pet-activity-card" key={a.id} onClick={()=>setActiveActivity(a)}><span className="pet-kicker">{tx(a.category)}・{sourceName(a.source_name)}</span><strong>{activityName(a)}</strong><span className="pet-one-line" title={activityDates(a.dates_text)}><Icon name="calendar" size={14}/>{activityDates(a.dates_text)}</span><small>{localText(a.venue_name,a.venue_name_en)}・{localText(a.fee_text,a.fee_text_en)}</small><span className="pet-activity-bottom">{a.registration_status==='full'?tx("已額滿"):a.registration_status==='open'?tx("接受報名"):a.remaining===null?tx("剩餘名額未提供"):count(a.remaining,'spots')}<span>{tx("睇詳情 ↗")}</span></span></button>)}
        {total>visibleCount && <button className="pet-more" onClick={()=>setVisibleCount(n=>n+40)}>{tx('睇多啲（尚有 {count} 個）',{count:total-visibleCount})}</button>}
        {isActivities && <details className="pet-transport"><summary>{tx("活動來源")}</summary>{catalog?.activity_sources.map(s=><article key={s.url}><a href={safeExternal(s.url)} target="_blank" rel="noopener noreferrer">{sourceName(s.name,s.name_en)} ↗</a><p>{s.integration==='official_link_only'?tx("主辦方不定期公佈；目前提供官方查詢入口。"):tx("已接入公開活動資料。")}</p></article>)}</details>}
        {(sourceProblem||snapshotOld) && <details className="pet-source-notice"><summary><Icon name="info" size={14}/>{snapshotOld?tx("資料快照較舊，等待同步任務更新。"):tx("部分來源暫時更新唔到。")}</summary><p>{relevantSources.filter(s=>s.status!=='ready').map(s=>`${tx(s.label)}: ${tx(s.message)}`).join(' ')}</p></details>}
        <footer className="pet-data-footer">{tx("快照：")}{updated(isActivities?activities?.fetched_at:places?.fetched_at)}<br/>{tx("政府同機構公開資料，唔係全港完整名單；圖層記錄可能重疊。")}<details><summary>{tx("睇資料來源同更新狀態")}</summary>{relevantSources.map(s=><p key={s.key}><a href={safeExternal(s.url)} target="_blank" rel="noopener noreferrer">{tx(s.label)} ↗</a>・{count(s.count,'records')}・{s.status==='ready'?tx("已同步"):s.status==='stale'?tx("舊快照"):tx("暫時讀唔到")}<br/>{updated(s.fetched_at)}</p>)}</details><details className="pet-project-info"><summary>{tx("項目源碼與授權")}</summary><p><a href="https://github.com/sammyliao1146-ship-it/hkpetmap" target="_blank" rel="noopener noreferrer">{tx("GitHub 專案源碼")} ↗</a> · <a href="https://github.com/sammyliao1146-ship-it/hkpetmap/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">MIT License ↗</a> · <a href="https://github.com/sammyliao1146-ship-it/hkpetmap/blob/main/docs/DATA_SOURCES.md" target="_blank" rel="noopener noreferrer">{tx("資料來源說明")} ↗</a></p><p>{tx("MIT 授權只適用於本項目程式碼；地圖底圖、第三方照片及上游資料按各自來源條款使用。")}</p></details></footer>
      </div>
      {activeActivity && isActivities && <section className="pet-detail" aria-label={tx("活動詳情")}><button className="pet-back" onClick={()=>setActiveActivity(null)}>{tx("‹ 返回活動列表")}</button><div className="pet-detail-scroll"><span className="pet-kicker">{tx(activeActivity.category)}</span><h2>{activityName(activeActivity)}</h2>{language==='zh-Hant' && activeActivity.name_en && <p className="muted">{activeActivity.name_en}</p>}<dl><dt>{tx("日期同課堂安排")}</dt><dd>{activityDates(activeActivity.dates_text)}</dd><dt>{tx("地點")}</dt><dd>{localText(activeActivity.venue_name,activeActivity.venue_name_en)}</dd><dt>{tx("費用")}</dt><dd>{localText(activeActivity.fee_text,activeActivity.fee_text_en)}</dd><dt>{tx("語言")}</dt><dd>{localText(activeActivity.language,activeActivity.language_en)}</dd><dt>{tx("報名狀態")}</dt><dd>{tx(activeActivity.registration_status==='full'?"已額滿":activeActivity.registration_status==='open'?"接受報名":"請向主辦方核實")}</dd><dt>{tx("剩餘名額")}</dt><dd>{activeActivity.remaining===null?tx("主辦方未有公開數量"):activeActivity.remaining}</dd><dt>{tx("活動簡介")}</dt><dd>{localText(activeActivity.description,activeActivity.description_en)}</dd><dt>{tx("參加條件")}</dt><dd>{localText(activeActivity.eligibility,activeActivity.eligibility_en)}</dd></dl><p className="muted">{tx("快照：")}{updated(activities?.fetched_at)}{tx("。日期保留主辦方原文，唔會推算未公佈嘅單堂日期。")}</p>{allPlaces.some(p=>p.id===activeActivity.place_id && p.latitude!==null) && <button className="pet-primary" onClick={()=>{const p=allPlaces.find(p=>p.id===activeActivity.place_id)!;setActivePlace(p);setPanel(null);}}>{tx("喺地圖睇上課地點")}</button>}<a className="pet-primary" href={safeExternal(activeActivity.booking_url || activeActivity.source_url)} target="_blank" rel="noopener noreferrer">{tx("去主辦方報名／查詢 ↗")}</a><p><a href={safeExternal(activeActivity.source_url)} target="_blank" rel="noopener noreferrer">{tx("來源：")}{sourceName(activeActivity.source_name,activeActivity.source_name_en)} ↗</a></p></div></section>}
      {activePlace && activePlace.latitude===null && !isActivities && <section className="pet-unmapped" role="status"><button className="icon-button" aria-label={tx("關閉地址提示")} onClick={()=>setActivePlace(null)}><Icon name="close" size={16}/></button><strong>{placeName(activePlace)}</strong><p>{tx("呢個地址未能可靠配對坐標，暫時唔會喺地圖落點。")}</p><a href={navigationUrl(activePlace)} target="_blank" rel="noopener noreferrer">{tx("用地址開啟導航核實 ↗")}</a></section>}
    </aside>}
    {panel===null && error && <div className="pet-map-warning" role="status">{errorText(error||tx("部分資料未能更新，請打開索引睇來源狀態。"))}</div>}
    <Suspense fallback={null}><AssistantPanel onShowPlace={showPlaceFromAssistant} open={assistantOpen} onOpen={()=>{setAssistantOpen(true);if(window.innerWidth<800)setPanel(null);}} onClose={()=>setAssistantOpen(false)}/></Suspense>
  </main>;
}
export default function App(){return <LanguageProvider><AppContent/></LanguageProvider>;}
