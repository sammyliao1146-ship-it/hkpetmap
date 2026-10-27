import type {PetPlace} from '../../api/client';
import Icon from '../../components/Icon';
import {facilityVisual} from '../../components/facility-categories';
import {getPetAmenities, petAmenities, type PetAmenity} from '../map/pet-amenities';
import {useLanguage} from '../../language';
import './explore.css';

/** Display shared parks within General parks without changing their access policy. */
export const groupedCategory=(key:string)=>key==='inclusive_parks'?'parks':key;

export default function ExploreCategories({places,categories,selectedAmenities,onCategoriesChange,onAmenitiesChange}: {
  places:PetPlace[];categories:string[]|null;selectedAmenities:PetAmenity[];
  onCategoriesChange:(value:string[]|null)=>void;onAmenitiesChange:(value:PetAmenity[])=>void;
}) {
  const {tx,category}=useLanguage();
  const keys=['pet_parks','parks','vets','hotels','malls','management','parking'];
  function toggle(key:string){
    const current=categories||keys;
    const next=current.includes(key)?current.filter(item=>item!==key):[...current,key];
    onCategoriesChange(next.length===keys.length?null:next);
    if(key==='pet_parks' && current.includes(key))onAmenitiesChange([]);
  }
  return <section className="pet-filters explore-place-categories">
    <div className="pet-section-heading"><h2>{tx('設施分類')}</h2><button onClick={()=>{onCategoriesChange(null);onAmenitiesChange([]);}}>{tx('重設')}</button></div>
    <label className="pet-checkbox"><input type="checkbox" checked={categories===null} onChange={e=>{onCategoriesChange(e.target.checked?null:[]);onAmenitiesChange([]);}}/><span>{tx('全部設施')}</span><em>{places.length}</em></label>
    {keys.map(key=><div key={key}>
      <label className="pet-checkbox"><input type="checkbox" checked={categories===null||categories.includes(key)} onChange={()=>toggle(key)}/><span className="facility-category-icon" style={{color:facilityVisual(key).color,background:facilityVisual(key).color+'12'}}><Icon name={facilityVisual(key).icon} size={21}/></span><span>{category(key)}</span><em>{places.filter(p=>groupedCategory(p.category)===key).length}</em></label>
      {key==='pet_parks' && (categories===null||categories.includes(key)) && <fieldset className="pet-amenity-filters explore-pet-park-amenities"><legend>{tx('寵物運動配套')}</legend>
        <ul className="pet-amenity-options pet-amenity-list">{petAmenities.map(item=><li key={item.key}><label className="pet-amenity-option"><input type="checkbox" checked={selectedAmenities.includes(item.key)} onChange={()=>{onCategoriesChange(['pet_parks']);onAmenitiesChange(selectedAmenities.includes(item.key)?selectedAmenities.filter(key=>key!==item.key):[...selectedAmenities,item.key]);}}/><span>{tx(item.label)}</span><em>{places.filter(p=>p.category==='pet_parks'&&getPetAmenities(p).includes(item.key)).length}</em></label></li>)}</ul>
      </fieldset>}
    </div>)}
    <p className="muted">{tx('一般公園包含寵物共享公園；各地點仍保留原有指定範圍及攜寵守則。')}</p>
  </section>;
}
