import {useState} from 'react';
import type {PetPlace} from '../api/client';
import {useLanguage, hasChinese} from '../language';
import {restaurantColor} from '../features/map/cuisine-colors';
import {getPetAmenities, petAmenities} from '../features/map/pet-amenities';
import {FacilityThumbnail} from './FacilityPhotos';
import {MallPolicyBadge} from './MallPolicy';
import Icon from './Icon';

export default function PlaceCard({place:p, selected, onSelect}: {place:PetPlace; selected:boolean; onSelect:()=>void}) {
  const {tx, language, placeName, placeAddress, districtName, category}=useLanguage();
  const [failed,setFailed]=useState(false);
  const d=p.restaurant_details;
  const restaurant=p.category==='restaurants';
  const photo=d?.photo_url?.startsWith('/api/v1/restaurant-photos/')?d.photo_url:null;
  const prices:Record<string,string>={PRICE_LEVEL_INEXPENSIVE:'$',PRICE_LEVEL_MODERATE:'$$',PRICE_LEVEL_EXPENSIVE:'$$$',PRICE_LEVEL_VERY_EXPENSIVE:'$$$$'};
  return <button className={`pet-place-card${selected?' selected':''}`} aria-pressed={selected} onClick={onSelect}>
    {restaurant?<span className="pet-card-media">
      {photo && !failed?<><img src={photo} alt={`${placeName(p)} · ${tx('場地相片')}`} loading="lazy" decoding="async" width={96} height={100} onError={()=>setFailed(true)}/><span className="pet-card-credit" title={`Google Maps · ${d?.photo_credit||''}`}>Google · {d?.photo_credit||'Maps'}</span></>:<span className="pet-card-placeholder" style={{color:restaurantColor(p)}}><Icon name="dining" size={30}/><small>{tx('暫未有相片')}</small></span>}
    </span>:<FacilityThumbnail key={p.id+':'+(p.photos?.[0]?.url||'')} place={p}/>}
    <span className="pet-card-copy"><strong>{placeName(p)}</strong>
      {restaurant && d?.rating!=null && <span className="pet-card-rating"><span aria-hidden="true">★</span><b>{d.rating.toFixed(1)}</b><span className="pet-card-reviews">({d.rating_count??0})</span>{d.price_level && prices[d.price_level] && <span className="pet-card-price">{prices[d.price_level]}</span>}</span>}
      <small className="pet-card-category">{restaurant && <i className="cuisine-swatch" style={{background:restaurantColor(p)}} aria-hidden="true"/>}{restaurant?(p.cuisines.length?p.cuisines:['未分類']).map(c=>tx(c)).join(' / '):category(p.category)}</small>
      <span className="pet-card-district"><Icon name="pin" size={12}/>{districtName(p.district)}</span>
      <span className="pet-address-line" title={placeAddress(p)}>{placeAddress(p)}</span>
      {!restaurant && <span className="pet-amenity-tags">{petAmenities.filter(item=>getPetAmenities(p).includes(item.key)).map(item=><span key={item.key}>{tx(item.label)}</span>)}</span>}
      <MallPolicyBadge place={p}/>
      {language==='en' && !p.address_en && hasChinese(p.address||'') && <small>{tx('地址只提供中文')}</small>}
      {p.latitude===null && <em>{tx('地址待定位・可開啟導航核實')}</em>}
    </span>
    <span className="pet-card-arrow" aria-hidden="true"><Icon name="chevron" size={16}/></span>
  </button>;
}
