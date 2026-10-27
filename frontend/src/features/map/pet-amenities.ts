import type {PetPlace} from '../../api/client';

export const petAmenities = [
  {key:'play_equipment', label:'寵物遊樂設施'},
  {key:'lawn', label:'活動草坪'},
  {key:'sandpit', label:'沙池'},
  {key:'wash', label:'寵物沖洗設施'},
] as const;
export type PetAmenity = typeof petAmenities[number]['key'];
const patterns: Record<PetAmenity, RegExp> = {
  play_equipment: /(?:寵物|狗隻|犬隻).{0,4}(?:遊樂設施|運動設施)|(?:pet|dog)\s+(?:playing|play|agility)\s+(?:equipment|facilities)/i,
  lawn: /(?:休憩草坪|草坪|草地|turf area|lawn)/i,
  sandpit: /沙池|sand\s*(?:pit|area)/i,
  wash: /(?:寵物|狗隻|犬隻).{0,5}(?:沖身|沖洗|淋浴)|(?:pet|dog).{0,12}(?:shower|wash)/i,
};

/** Positive source descriptions only; an ordinary park's lawn is not a dog lawn. */
export function getPetAmenities(place: Pick<PetPlace,'category'|'notes'|'notes_en'>): PetAmenity[] {
  if(!['pet_parks','inclusive_parks'].includes(place.category))return [];
  const clauses=[...(place.notes||[]),...(place.notes_en||[])].flatMap(note=>note.split(/[，,、；;。\n]/));
  return petAmenities.filter(({key})=>clauses.some(clause=>{
    const match=patterns[key].exec(clause);
    if(!match)return false;
    if(/(?:沒有|不設|未設|無|暫停|不提供|不開放|no\b|without\b|closed|unavailable)/i.test(clause.slice(Math.max(0,match.index-25),match.index)))return false;
    if(/^(?:.{0,3})(?:暫停|關閉|不開放|closed|unavailable)/i.test(clause.slice(match.index+match[0].length)))return false;
    if(place.category==='inclusive_parks' && key==='lawn' && !/(?:寵物|狗隻|犬隻|pet|dog)/i.test(clause))return false;
    return true;
  })).map(({key})=>key);
}
