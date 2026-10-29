import {readChatEvents} from './sse-reader';
export interface SourceStatus { key: string; label: string; url: string; status: string; count: number; fetched_at: string | null; message: string; skipped: number; }
export interface MallPolicy {
  tier: 'on_leash_full'|'designated_zone'|'carrier_only'|'unknown';
  verification: 'official_checked'|'third_party'; listing_url: string;
  listing_updated_at: string; checked_at: string|null; official_policy_url: string|null;
  venue_kind: 'shopping_mall'|'retail_precinct'|'department_store'|'commercial_building'|'retail_destination';
}
export interface RestaurantDetails {
 google_place_id:string; display_name?:string|null; display_name_language?:string|null;
 google_address?:string|null; match_status?:string; match_distance_m?:number|null; rating:number|null; rating_count:number|null; price_level:string|null;
 price_range:{startPrice?:{currencyCode?:string;units?:string;nanos?:number};endPrice?:{currencyCode?:string;units?:string;nanos?:number}}|null;
 website:string|null; telephone:string|null; hours:string[]; reservable:boolean|null;
 booking_url:string|null; menu_url:string|null; google_maps_url:string|null; reviews_url:string|null;
 dish_photo_url?:string|null; dish_photo_source_url?:string|null; dish_photo_credit?:string|null; dish_photo_kind?:string|null;
 photo_url:string|null; photo_source_url:string|null; photo_credit:string|null; fetched_at:string|null;
 reviews:{author:string;author_url?:string|null;rating?:number|null;text?:string|null;original_text?:string|null;original_language?:string|null;published_at?:string|null;url?:string|null}[];
}
export interface PetPlace {
  detail_loaded?:boolean;
  restaurant_details?:RestaurantDetails|null;
  mall_policy?: MallPolicy|null;
  photos?: {url: string; source_url: string; credit: string; alt: string; authors?: {displayName?:string;uri?:string}[]}[];
  id: string; category: string; name: string; name_en: string | null; district: string | null;
  address: string | null; address_en: string | null; latitude: number | null; longitude: number | null;
  website_en?: string | null; rules_url_en?: string | null;
  notes_en?: string[]; opening_hours_en?: string | null; source_name_en?: string | null;
  coordinate_source: string | null; cuisines: string[]; cuisine_source: string | null; telephone: string | null;
  opening_hours: string | null; website: string | null; source_url: string; source_name: string;
  source_updated_at: string | null; licence_number: string | null; pet_policy: string; notes: string[]; rules_url: string | null;
}
export interface PetActivity {
  description_en?: string | null; eligibility_en?: string | null; fee_text_en?: string | null; language_en?: string | null; venue_name_en?: string | null; source_name_en?: string | null;
  id: string; name: string; name_en: string | null; category: string; dates_text: string;
  start_date: string | null; end_date: string | null; venue_name: string | null; place_id: string | null;
  district: string | null; language: string | null; fee_text: string | null; description: string;
  registration_status?: 'unknown' | 'open' | 'full' | 'cancelled';
  eligibility: string | null; remaining: number | null; source_url: string; booking_url: string | null; source_name: string;
}
export interface PlaceCollection { revision?:string; status: string; fetched_at: string | null; items: PetPlace[]; total: number; mapped: number; sources: SourceStatus[]; }
export interface ActivityCollection { status: string; fetched_at: string | null; items: PetActivity[]; total: number; message: string; }
export interface Catalog {
  status: string; fetched_at: string | null; categories: {key: string; label: string}[]; cuisines: string[];
  sources: SourceStatus[]; transport_services: {name: string; name_en?: string; url: string; notes: string; notes_en?: string}[];
  activity_sources: {name: string; name_en?: string; url: string; integration: string}[]; message: string;
}
async function request<T>(path: string, options?: RequestInit, fallback?:string): Promise<T> {
  let response = await fetch(`/api/v1${path}`, options);
  if(response.status===404&&fallback)response=await fetch(`/api/v1${fallback}`,options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : '暫時讀唔到資料，請稍後再試。');
  }
  return response.json() as Promise<T>;
}
export const getCatalog = (signal?: AbortSignal, revision='') => request<Catalog>('/catalog'+(revision?'?v='+encodeURIComponent(revision):''), {signal});
let placeRevision='';
export const photoDataVersion=()=>placeRevision;
const detailCache=new Map<string,PetPlace>();
export async function getPlaces(signal?:AbortSignal) {
  const data=await request<PlaceCollection>('/place-summaries',{signal},'/places');
  if(data.revision!==placeRevision){detailCache.clear();placeRevision=data.revision||'';}
  return data;
}
export async function getDataVersion(signal?:AbortSignal):Promise<{revision:string}> {
  const response=await fetch('/api/v1/data-version',{signal});
  if(response.status===404)return {revision:'legacy'}; // Allow frontend/backend rolling deploys.
  if(!response.ok)throw new Error('Unable to check data version. Please try again.');
  return response.json();
}
export async function getPlaceDetails(id:string,signal?:AbortSignal) {
  const key=placeRevision+':'+id;
  const cached=detailCache.get(key);if(cached)return cached;
  const data=await request<PlaceCollection>('/places/'+encodeURIComponent(id),{signal});
  const place=data.items[0];if(!place)throw new Error('Place not found');
  if(key.startsWith(placeRevision+':')){
    if(detailCache.size>=64)detailCache.delete(detailCache.keys().next().value!);
    detailCache.set(key,place);
  }
  return place;
}
export const getActivities = (signal?: AbortSignal) => request<ActivityCollection>('/activities', {signal});
export interface ChatMessage { role: 'user' | 'assistant'; content: string; }
export interface ChatOrigin {latitude:number;longitude:number;}
let sessionId = crypto.randomUUID();
export const newChatSession = () => { sessionId = crypto.randomUUID(); };
export const chat = (message: string, history: ChatMessage[] = [], language: 'zh-Hant'|'en' = 'zh-Hant', origin?:ChatOrigin|null) => request<ChatResult>('/assistant/chat', {
  method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message,history,language,session_id:sessionId,...(origin?{origin}:{})}),
});
export interface ChatResult {answer: string; model: string; sources?: {title:string;url:string}[]; places?: {id:string;name:string}[]; degraded?: boolean}
export async function chatStream(message: string, history: ChatMessage[], language: 'zh-Hant'|'en', origin: ChatOrigin|null|undefined, onDelta: (text:string)=>void): Promise<ChatResult> {
  const response = await fetch('/api/v1/assistant/chat/stream', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message,history,language,session_id:sessionId,...(origin?{origin}:{})}),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : '暫時讀唔到資料，請稍後再試。');
  }
  return readChatEvents<ChatResult>(response.body,onDelta,language==='en'
    ? 'The connection ended without a complete answer. Please try again.'
    : '連線中斷，未收到完整回覆，請重試。');
}

export const prefillNearby = (origin: ChatOrigin, language: 'zh-Hant'|'en') => request<{cached:boolean;count:number}>('/assistant/prefill', {
  method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...origin,language}),
}).catch(() => undefined);

export interface ParkingCollection {status:string; fetched_at:string|null; items:PetPlace[]; total:number;}
export const getParking = (signal?:AbortSignal, language:'en'|'zh-Hant'='en') => request<ParkingCollection>(`/parking?language=${language}`, {signal});
