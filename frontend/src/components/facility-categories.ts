import type {IconName} from './Icon';

export const facilityVisuals: Record<string, {icon: IconName; color: string}> = {
  parks: {icon:'park', color:'#70866d'},
  pet_parks: {icon:'pet-park', color:'#286b47'},
  inclusive_parks: {icon:'park', color:'#70866d'},
  vets: {icon:'vet', color:'#3976a5'},
  hotels: {icon:'boarding', color:'#8b5ba8'},
  management: {icon:'animal-care', color:'#317f83'},
  malls: {icon:'mall', color:'#ba527f'},
  parking: {icon:'parking', color:'#365c69'},
};
export function facilityVisual(category: string) {
  return facilityVisuals[category] || {icon:'pin' as const, color:'#286b47'};
}
