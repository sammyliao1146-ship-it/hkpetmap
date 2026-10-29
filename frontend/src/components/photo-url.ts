import {photoDataVersion} from '../api/client';
/** External source images retain their own URLs and policies. */
export function photoVariant(url:string, size:'thumb'|'detail') {
  if(!/^\/api\/v1\/(?:restaurant-photos|restaurant-dish-photos|facility-photos)\/[A-Za-z0-9_-]+$/.test(url))return url;
  const version=photoDataVersion();
  return `${url}?size=${size}${version?'&v='+encodeURIComponent(version):''}`;
}
