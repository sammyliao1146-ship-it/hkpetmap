import type { ChatOrigin, PetActivity, PetPlace } from './client';

export type PlanRegion = 'any' | 'hong_kong_island' | 'kowloon' | 'new_territories';
export type PlanInterest = 'park' | 'vet' | 'activity' | 'mall';
export interface PlanParking {
  id: string;
  name: string;
  name_en?: string | null;
  address?: string | null;
  address_en?: string | null;
  latitude: number;
  longitude: number;
  vacancy?: number | null;
  vacancy_updated_at?: string | null;
  vacancy_stale?: boolean;
  vacancy_status?: 'available' | 'full' | 'stale' | 'unknown';
  stale?: boolean;
  fee_summary?: string | null;
  hourly_rate?: number | null;
  height_limit?: number | null;
  source_url?: string;
  navigation_url?: string;
  [key: string]: unknown;
}
export interface PlanStop {
  place: PetPlace;
  purpose: string;
  distance_from_parking_m?: number;
  distance_m?: number;
  activity?: PetActivity | null;
  mall_policy_summary?: string | null;
}
export interface ParkingGroup {
  parking: PlanParking;
  radius_m: number;
  stops: PlanStop[];
}
export interface TripPlan {
  id: string;
  status: 'ready' | 'partial' | 'no_results';
  title: string;
  summary: string;
  date: string;
  region: string;
  destination?: {id: string; name: string; name_en?: string; [key: string]: unknown} | null;
  parking_groups: ParkingGroup[];
  map_places: PetPlace[];
  warnings: string[];
  sources?: {title: string; url: string}[];
}
export interface PlanRequest {
  date: string;
  region: PlanRegion;
  interests: PlanInterest[];
  cuisine: string;
  random: boolean;
  destination_id?: string;
  origin?: ChatOrigin;
  language: 'en' | 'zh-Hant';
}
export async function createPlan(payload: PlanRequest, signal?: AbortSignal): Promise<TripPlan> {
  const response = await fetch('/api/v1/plans', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to create a plan. Please try again.');
  return body;
}
