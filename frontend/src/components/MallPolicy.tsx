import type {PetPlace} from '../api/client';
import {useLanguage} from '../language';
import {safeExternal} from '../features/map/venue-links';
const tierLabels:Record<string,string>={on_leash_full:'目錄分類：可牽繩落地',designated_zone:'指定區域／樓層',carrier_only:'需寵物車／袋',unknown:'攜寵規則待確認'};
export function MallPolicyBadge({place}:{place:PetPlace}){
 const {tx}=useLanguage();const policy=place.mall_policy;
 if(!policy)return null;
 return <span className={`mall-policy-badge mall-policy-${policy.tier}`}>{tx(tierLabels[policy.tier]||tierLabels.unknown)} · {tx(policy.verification==='official_checked'?'已核對官方規則':'第三方資料・待確認')}</span>;
}
export default function MallPolicyDetails({place}:{place:PetPlace}){
 const {tx}=useLanguage();const policy=place.mall_policy;
 if(!policy)return null;
 return <div className="mall-policy-details">
   <MallPolicyBadge place={place}/>
   {policy.verification==='third_party' && <p>{tx('目錄分類未經獨立核實，出發前請向場地確認。')}</p>}
   <p>{tx('目錄資料日期：')}{policy.listing_updated_at}</p>
   {policy.checked_at && <p>{tx('官方規則核對日期：')}{policy.checked_at}</p>}
   {safeExternal(policy.official_policy_url) && <p><a href={safeExternal(policy.official_policy_url)} target="_blank" rel="noopener noreferrer">{tx('官方攜寵規則 ↗')}</a></p>}
   <p><a href={safeExternal(policy.listing_url)} target="_blank" rel="noopener noreferrer">{tx('商場目錄來源 ↗')}</a></p>
 </div>;
}
