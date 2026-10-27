import { useEffect, useRef, useState, type FormEvent } from 'react';
import { createPlan, type PlanInterest, type PlanRegion, type TripPlan } from '../../api/plans';
import type { PetPlace } from '../../api/client';
import Icon from '../../components/Icon';
import { safeExternal } from '../map/venue-links';
import { useLanguage } from '../../language';
import './plan.css';

const regions: [PlanRegion, string, string][] = [
  ['any', 'Anywhere in Hong Kong', '香港全區'], ['hong_kong_island', 'Hong Kong Island', '港島'],
  ['kowloon', 'Kowloon', '九龍'], ['new_territories', 'New Territories & Islands', '新界及離島'],
];
const interests: [PlanInterest, string, string][] = [
  ['park', 'Parks & waterfronts', '公園及海濱'], ['vet', 'Vet visit', '獸醫／醫院'],
  ['activity', 'Activities', '活動'], ['mall', 'Shopping malls', '商場'],
];
const todayHK = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Hong_Kong', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());

export default function PlanPanel({onPlanChange, onSelectPlace, cuisineOptions}: {
  onPlanChange: (plan: TripPlan | null) => void;
  onSelectPlace: (place: PetPlace) => void;
  cuisineOptions: string[];
}) {
  const {language, placeName, errorText, tx} = useLanguage();
  const text = (en: string, zh: string) => language === 'en' ? en : zh;
  const [date, setDate] = useState(todayHK);
  const [region, setRegion] = useState<PlanRegion>('any');
  const [selected, setSelected] = useState<PlanInterest[]>(['park']);
  const [cuisine, setCuisine] = useState('');
  const [random, setRandom] = useState(false);
  const [plan, setPlan] = useState<TripPlan | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const resultRef = useRef<HTMLElement | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { if (plan) resultRef.current?.scrollIntoView({block:'start', behavior:'smooth'}); }, [plan?.id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || !selected.length) return;
    const request = new AbortController(); controller.current = request;
    setPending(true); setError('');
    try {
      const result = await createPlan({date, region, interests:selected, cuisine, random, language}, request.signal);
      setPlan(result); onPlanChange(result);
    } catch (reason) {
      if (!request.signal.aborted) setError(errorText(reason instanceof Error ? reason.message : 'Unable to create a plan. Please try again.'));
    } finally { if (!request.signal.aborted) setPending(false); }
  }

  return <aside className="pet-sidebar plan-sidebar" aria-label={text('Plan your pet outing', '規劃毛孩出遊')}>
    <div className="plan-heading"><span className="eyebrow">{text('A LITTLE ADVENTURE, TOGETHER', '一齊出發去玩')}</span>
      <h1>{text('Plan a day out', '規劃毛孩出遊')}</h1><p>{text('Choose a date, an area and a few things you love.', '揀日期、地區同想做嘅事。')}</p>
    </div>
    <div className="plan-scroll" ref={scrollRef}>
      <form className="plan-form" onSubmit={submit}>
        <div className="plan-field-row"><label>{text('Date', '日期')}<input type="date" required value={date} onChange={e=>setDate(e.target.value)}/></label>
          <label>{text('Area', '地區')}<select aria-label={text('Area', '地區')} value={region} onChange={e=>setRegion(e.target.value as PlanRegion)}>{regions.map(([key,en,zh])=><option key={key} value={key}>{text(en,zh)}</option>)}</select></label></div>
        <fieldset><legend>{text('What would you like to do?', '想做啲咩？')}</legend><div className="plan-interest-grid">{interests.map(([key,en,zh])=><label className={selected.includes(key)?'selected':''} key={key}>
          <input type="checkbox" checked={selected.includes(key)} onChange={()=>setSelected(current=>current.includes(key)?current.filter(v=>v!==key):[...current,key])}/>{text(en,zh)}</label>)}</div></fieldset>
        <label>{text('Then, something to eat', '之後食啲咩？')}<select aria-label={text('Then, something to eat', '之後食啲咩？')} value={cuisine} onChange={e=>setCuisine(e.target.value)}><option value="">{text('Any cuisine', '不限菜系')}</option>{cuisineOptions.map(value=><option key={value} value={value}>{tx(value)}</option>)}</select></label>
        <label className="plan-random"><input type="checkbox" checked={random} onChange={e=>setRandom(e.target.checked)}/><span>{text('Surprise me with a destination', '隨機幫我揀目的地')}</span><Icon name="sparkles" size={16}/></label>
        {random && <p className="plan-help">{text('Pick from our waterfront and park destinations, within your selected area.', '由之前介紹嘅海濱同公園目的地中，按所選地區隨機揀選。')}</p>}
        <p className="plan-help">{text('Each parking stop groups places within 1 km. More parking stops may be included when needed.', '每個停車點會集合一公里內嘅地點；需要時會安排多個停車點。')}</p>
        <button className="plan-submit" type="submit" disabled={pending || !selected.length}><Icon name={pending?'clock':'directions'} size={17}/>{pending?text('Putting your plan together…', '安排緊行程…'):text(plan?'Make a new plan':'Create my plan', plan?'重新規劃':'規劃行程')}</button>
        {!selected.length && <p className="plan-help">{text('Choose at least one activity.', '請最少揀一項活動。')}</p>}
      </form>
      {error && <p className="inline-error" role="alert">{error}</p>}
      {pending && <p className="plan-progress" role="status">{text('Checking places and nearby parking, then asking the outing agent to arrange your stops.', '查緊地點同附近停車場，再由助手安排各站。')}</p>}
      {plan && <section className="plan-result" ref={resultRef} aria-live="polite"><div className="plan-result-heading"><span className="eyebrow">{text('YOUR OUTING', '今次行程')}</span><button type="button" className="plan-edit" onClick={()=>scrollRef.current?.scrollTo({top:0,behavior:'smooth'})}>{text('Edit choices', '修改條件')}</button><h2>{plan.title}</h2><p>{plan.summary}</p></div>
        {plan.parking_groups.map((group,index)=><article className="plan-parking-group" key={`${group.parking.id}:${index}`}>
          <header><span className="plan-parking-letter">P{index+1}</span><div><h3>{language==='en'?(group.parking.name_en||group.parking.name):group.parking.name}</h3><span>{text('1 km discovery area', '一公里出遊範圍')}</span></div></header>
          {group.parking.address && <p className="plan-parking-address">{language==='en'?(group.parking.address_en||group.parking.address):group.parking.address}</p>}
          {group.parking.fee_summary && <p className="plan-parking-address">{group.parking.fee_summary}</p>}
          <p className="plan-parking-address">{group.parking.vacancy_status==='stale'||group.parking.stale
            ?text('Vacancy data is out of date', '空位資料已過期')
            :group.parking.vacancy!=null?`${group.parking.vacancy} ${text('spaces reported', '個空位')}`:text('Vacancy not available', '未有空位資料')}</p>
          <ol>{group.stops.map((stop,stopIndex)=><li key={`${stop.place.id}:${stopIndex}`}><button type="button" onClick={()=>onSelectPlace(stop.place)}><span className="plan-stop-number">{stopIndex+1}</span><span><strong>{placeName(stop.place)}</strong><small>{stop.place.category==='restaurants'?text('Food stop', '食飯'):stop.purpose==='activity'?text('Activity', '活動'):text('Explore', '探索')}{(stop.distance_m??stop.distance_from_parking_m)!=null && ` · ${Math.round((stop.distance_m??stop.distance_from_parking_m)!)} m`}</small></span><Icon name="pin" size={15}/></button>
            {stop.place.category==='malls' && stop.mall_policy_summary && <p className="plan-mall-rule">{stop.mall_policy_summary}</p>}
            {stop.activity && <p className="plan-activity-date">{stop.activity.dates_text}</p>}
          </li>)}</ol>
          <a className="plan-parking-navigation" href={safeExternal(group.parking.navigation_url)||`https://www.google.com/maps/dir/?api=1&destination=${group.parking.latitude},${group.parking.longitude}&travelmode=driving`} target="_blank" rel="noopener noreferrer"><Icon name="directions" size={15}/>{text('Drive to this car park', '導航去呢個停車場')}</a>
        </article>)}
        {!!plan.warnings?.length && <div className="plan-notices">{plan.warnings.map((warning,index)=><p key={index}>{warning}</p>)}</div>}
        {plan.sources && plan.sources.length>0 && <details className="plan-sources"><summary>{text('Sources', '資料來源')}</summary>{plan.sources.map((source,index)=>safeExternal(source.url)&&<a key={index} href={safeExternal(source.url)} target="_blank" rel="noopener noreferrer">{source.title||text('Source', '來源')} ↗</a>)}</details>}
      </section>}
    </div>
  </aside>;
}
