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
export interface PlaceCollection { status: string; fetched_at: string | null; items: PetPlace[]; total: number; mapped: number; sources: SourceStatus[]; }
export interface ActivityCollection { status: string; fetched_at: string | null; items: PetActivity[]; total: number; message: string; }
export interface Catalog {
  status: string; fetched_at: string | null; categories: {key: string; label: string}[]; cuisines: string[];
  sources: SourceStatus[]; transport_services: {name: string; name_en?: string; url: string; notes: string; notes_en?: string}[];
  activity_sources: {name: string; name_en?: string; url: string; integration: string}[]; message: string;
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : '暫時讀唔到資料，請稍後再試。');
  }
  return response.json() as Promise<T>;
}
export const getCatalog = (signal?: AbortSignal) => request<Catalog>('/catalog', {signal});
export const getPlaces = (signal?: AbortSignal) => request<PlaceCollection>('/places', {signal});
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
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let final: ChatResult | null = null;
  const handle = (block: string) => {
    const line = block.split('\n').find(l => l.startsWith('data: '));
    if (!line) return;
    const event = JSON.parse(line.slice(6));
    if (event.type === 'delta') onDelta(event.text);
    else if (event.type === 'final') final = event;
    else if (event.type === 'error') throw new Error(typeof event.detail === 'string' ? event.detail : '暫時連唔到助手，請再試。');
  };
  try {
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf('\n\n')) >= 0) { handle(buffer.slice(0, index)); buffer = buffer.slice(index + 2); }
    if (done) break;
  }
  if(buffer.trim())handle(buffer);
  if (!final) throw new Error('暫時連唔到助手，請再試。');
  return final;
  } finally { reader.releaseLock(); }
}
export const prefillNearby = (origin: ChatOrigin, language: 'zh-Hant'|'en') => request<{cached:boolean;count:number}>('/assistant/prefill', {
  method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...origin,language}),
}).catch(() => undefined);

export interface ParkingCollection {status:string; fetched_at:string|null; items:PetPlace[]; total:number;}
export const getParking = (signal?:AbortSignal, language:'en'|'zh-Hant'='en') => request<ParkingCollection>(`/parking?language=${language}`, {signal});
