import type { PetPlace } from '../../api/client';
export function navigationUrl(place: PetPlace) {
  // Opening Google Maps does not assert that the route allows pets.
  const destination = `${place.name} ${place.address || place.address_en || ''}`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}`;
}
export function safeExternal(value: string | null | undefined) {
  try { const u = new URL(value || ''); return u.protocol === 'https:' && !u.username && !u.password ? u.href : undefined; }
  catch { return undefined; }
}
