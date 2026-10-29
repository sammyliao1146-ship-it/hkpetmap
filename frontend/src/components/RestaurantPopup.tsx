import {photoVariant} from './photo-url';
import {useState} from 'react';
import type {PetPlace} from '../api/client';
import {useLanguage,formatOpeningHours} from '../language';
import Icon from './Icon';
import {safeExternal,navigationUrl} from '../features/map/venue-links';

function external(url?:string|null){return safeExternal(url);}
export default function RestaurantPopup({place}:{place:PetPlace}) {
 const {tx,language,placeName,placeAddress}=useLanguage();
 const d=place.restaurant_details;const [imageFailed,setImageFailed]=useState(false);const [dishFailed,setDishFailed]=useState(false);
 const level:Record<string,string>={PRICE_LEVEL_FREE:tx('免費'),PRICE_LEVEL_INEXPENSIVE:'$',PRICE_LEVEL_MODERATE:'$$',PRICE_LEVEL_EXPENSIVE:'$$$',PRICE_LEVEL_VERY_EXPENSIVE:'$$$$'};
 const range=d?.price_range;
 function money(p?:{currencyCode?:string;units?:string;nanos?:number}){if(!p)return '';const amount=Number(p.units||0)+(p.nanos||0)/1e9;return new Intl.NumberFormat(language==='en'?'en-HK':'zh-HK',{style:'currency',currency:p.currencyCode||'HKD',maximumFractionDigits:2,minimumFractionDigits:0}).format(amount);}
 const price=range?.startPrice||range?.endPrice?[money(range.startPrice),money(range.endPrice)].filter(Boolean).join('–'):(d?.price_level?level[d.price_level]:'');
 const telephone=d?.telephone||place.telephone;const phone=telephone?.replace(/[^+0-9]/g,'');
 const website=external(d?.website||place.website);const booking=external(d?.booking_url);const menu=external(d?.menu_url);
 const photo=d?.photo_url?.startsWith('/api/v1/restaurant-photos/')?d.photo_url:null;
 const dish=d?.dish_photo_url?.startsWith('/api/v1/restaurant-dish-photos/')?d.dish_photo_url:null;
 return <section className="restaurant-popup">
  <div className={dish && !dishFailed?'restaurant-photo-grid has-dish':'restaurant-photo-grid'}>
  {photo && !imageFailed?<figure className="restaurant-hero"><img src={photoVariant(photo,'detail')} alt={`${placeName(place)} · ${tx('場地相片')}`} onError={()=>setImageFailed(true)}/><figcaption><a href={external(d?.photo_source_url)} target="_blank" rel="noopener noreferrer">Google Maps · {d?.photo_credit}</a></figcaption></figure>:<div className="restaurant-photo-empty">{tx('暫未有相片')}</div>}
  {dish && !dishFailed && <figure className="restaurant-hero restaurant-dish-photo"><a href={dish} target="_blank" rel="noopener noreferrer"><img src={photoVariant(dish,'detail')} alt={`${placeName(place)} · ${tx(d?.dish_photo_kind==='drink'?'飲品照片':'菜品照片')}`} onError={()=>setDishFailed(true)}/></a><span className="dish-photo-label">{tx(d?.dish_photo_kind==='drink'?'飲品照片':'菜品照片')}</span><figcaption><a href={external(d?.dish_photo_source_url)} target="_blank" rel="noopener noreferrer">Google Maps · {d?.dish_photo_credit}</a></figcaption></figure>}
  </div>
  <div className="restaurant-heading"><span className="pet-kicker">{tx('狗友善餐廳')}</span><h3>{placeName(place)}</h3>
   {d?.match_status==='needs_review' && <small className="restaurant-match-note">{tx('Google 候選資料・待核對')}</small>}
   <div className="restaurant-rating">{d?.rating!=null?<><strong>{d.rating.toFixed(1)}</strong><span className="restaurant-stars" style={{background:`linear-gradient(90deg,#d29c24 ${d.rating/5*100}%,#dce0da ${d.rating/5*100}%)`,backgroundClip:'text',color:'transparent'}} aria-label={`${d.rating} / 5`}>★★★★★</span><a href={external(d.reviews_url||d.google_maps_url)} target="_blank" rel="noopener noreferrer">({d.rating_count??0}) · Google</a></>:<span>{tx('評分未提供')}</span>}{price && <span className="restaurant-price">{price}</span>}</div>
   <div className="restaurant-cuisines">{(place.cuisines.length?place.cuisines:['未分類']).map(c=><span key={c}>{tx(c)}</span>)}</div>
  </div>
  <nav className="restaurant-actions" aria-label={tx('餐廳連結')}>
   <a href={navigationUrl(place)} target="_blank" rel="noopener noreferrer"><Icon name="directions" size={15}/>{tx('導航')}</a>
   {menu?<a href={menu} target="_blank" rel="noopener noreferrer"><Icon name="menu-book" size={15}/>{tx('菜單')}</a>:<span>{tx('菜單未提供')}</span>}
   {booking?<a href={booking} target="_blank" rel="noopener noreferrer"><Icon name="reservation" size={15}/>{tx('訂位')}</a>:phone?<a href={`tel:${phone}`}><Icon name="phone" size={15}/>{tx(d?.reservable?'致電訂位':'致電查詢')}</a>:<span>{tx('訂位資訊未提供')}</span>}
   {website && <a href={website} target="_blank" rel="noopener noreferrer"><Icon name="globe" size={15}/>{tx('官網')}</a>}
  </nav>
  <p className="restaurant-address">{d?.match_status==='needs_review' && <span>{tx('原名單地址：')}</span>}{placeAddress(place)}</p>
  {d?.match_status==='needs_review' && d.google_address && <p className="restaurant-candidate-address">{tx('Google 候選地址：')}{d.google_address}</p>}
  {telephone && <p><span className="restaurant-field-label">{tx('電話：')}</span><a href={`tel:${phone}`}>{telephone}</a></p>}
  <p className="restaurant-pet-note"><Icon name="paw" size={16}/>{tx('准許狗隻進入，入場條件請向餐廳確認。')}</p>
  {d?.hours?.length ? <details className="restaurant-hours"><summary>{tx('營業時間')}</summary>{d.hours.map(h=><div key={h}>{formatOpeningHours(h,language)}</div>)}</details>:null}
  {d?.reviews?.length ? <details className="restaurant-reviews"><summary>{tx('Google 評價')} · {d.reviews.length}</summary>{d.reviews.map((r,i)=><article key={`${r.author}-${i}`}><header><a href={external(r.author_url||r.url)} target="_blank" rel="noopener noreferrer">{r.author}</a><span>★ {r.rating??'—'}</span></header>{(r.text||r.original_text)&&<p>{language==='en' && r.original_language?.startsWith('en')?r.original_text:r.text||r.original_text}</p>}{r.published_at&&<small>{new Date(r.published_at).toLocaleDateString(language==='en'?'en-HK':'zh-HK')}</small>}</article>)}{external(d.reviews_url)&&<a href={external(d.reviews_url)} target="_blank" rel="noopener noreferrer">{tx('查看更多評價 ↗')}</a>}</details>:null}
  {d?.fetched_at && <small className="restaurant-freshness">{tx('Google 資料擷取於：')}{new Date(d.fetched_at).toLocaleDateString(language==='en'?'en-HK':'zh-HK',{year:'numeric',month:'long',timeZone:'Asia/Hong_Kong'})} · {tx('非即時資料')}</small>}
  {!d && <small>{tx('尚未可靠配對 Google 餐廳資料')}</small>}
  <details className="restaurant-sources"><summary>{tx('牌照與資料來源')}</summary><p>{tx('原名單名稱：')}{place.name}{place.name_en && place.name_en!==place.name?` / ${place.name_en}`:''}</p>{place.licence_number&&<p>{tx('牌照號碼：')}{place.licence_number}</p>}<p><a href={external(place.source_url)} target="_blank" rel="noopener noreferrer">{tx('官方餐廳名單 ↗')}</a></p>{external(place.cuisine_source)&&<p><a href={external(place.cuisine_source)} target="_blank" rel="noopener noreferrer">{tx('分類來源 ↗')}</a></p>}{external(d?.google_maps_url)&&<p><a href={external(d?.google_maps_url)} target="_blank" rel="noopener noreferrer">Google Maps ↗</a></p>}<small>{tx('地圖標記係場地代表點，唔一定係入口。導航路線唔保證可以攜寵。')}</small></details>
 </section>;
}
