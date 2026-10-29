import {photoVariant} from './photo-url';
import {useState} from 'react';
import type {PetPlace} from '../api/client';
import Icon from './Icon';
import {facilityVisual} from './facility-categories';
import {useLanguage} from '../language';
import {safeExternal} from '../features/map/venue-links';

function photoUrl(value?:string) {return value && /^\/api\/v1\/facility-photos\/[0-9a-f]{24}$/.test(value)?value:safeExternal(value);}

export function FacilityThumbnail({place}: {place:PetPlace}) {
  const {language,tx,placeName}=useLanguage();
  const [failed,setFailed]=useState(false);
  const photo=place.photos?.[0];
  const visual=facilityVisual(place.category);
  const url=photoUrl(photo?.url);
  return <span className="facility-thumbnail">{url && !failed
    ? <img key={url} src={photoVariant(url,'thumb')} alt={language==='en'?`${placeName(place)} — venue photo`:photo?.alt || `${place.name}・場地相片`} loading="lazy" decoding="async" width={88} height={72} referrerPolicy="no-referrer" onError={()=>setFailed(true)}/>
    : <span className="facility-photo-placeholder" style={{color:visual.color,background:visual.color+'0a'}}><Icon name={visual.icon} size={30}/><span>{tx("暫未有相片")}</span></span>}</span>;
}
function Photo({photo,place}: {photo:NonNullable<PetPlace['photos']>[number];place:PetPlace}) {
  const {language,tx,placeName}=useLanguage();
  const [failed,setFailed]=useState(false);
  const url=photoUrl(photo.url);
  if(!url || failed)return null;
  return <figure><a href={url} target="_blank" rel="noopener noreferrer"><img src={photoVariant(url,'detail')} alt={language==='en'?`${placeName(place)} — venue photo`:photo.alt} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={()=>setFailed(true)}/></a><figcaption><a href={safeExternal(photo.source_url)} target="_blank" rel="noopener noreferrer">{tx("相片：")}{tx(photo.credit)} ↗</a>{photo.authors?.map((author,i)=><span key={i}> · <a href={safeExternal(author.uri)} target="_blank" rel="noopener noreferrer">{author.displayName}</a></span>)}</figcaption></figure>;
}
export function FacilityGallery({place}: {place:PetPlace}) {
  const {tx,placeName}=useLanguage();
  if(!place.photos?.length)return place.category==='restaurants'?null:<p className="facility-no-photo">{tx("來源暫未提供已配對嘅場地相片")}</p>;
  return <div className="facility-photo-gallery" aria-label={`${placeName(place)} — ${tx('場地相片')}`}>{place.photos.slice(0,2).map(p=><Photo key={p.url} photo={p} place={place}/>)}</div>;
}
