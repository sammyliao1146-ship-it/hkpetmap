import type { CSSProperties, ReactNode } from 'react';

export type IconName = 'menu' | 'close' | 'search' | 'chevron' | 'chevron-left' | 'clock' | 'sparkles' | 'chat' | 'wave' | 'track' | 'trail' | 'tent' | 'calendar' | 'send' | 'pin' | 'layers' | 'activity' | 'ball' | 'fitness' | 'tree' | 'info' | 'park' | 'pet-park' | 'shared-park' | 'vet' | 'boarding' | 'animal-care' | 'mall' | 'directions' | 'menu-book' | 'reservation' | 'phone' | 'globe' | 'paw' | 'dining' | 'parking';
const paths: Record<IconName, ReactNode> = {
  parking: <><rect x="3" y="3" width="18" height="18" rx="4"/><path d="M9 18V7h4a3 3 0 0 1 0 6H9"/></>,
  dining: <><path d="M4 3v5c0 3 6 3 6 0V3M7 3v18M20 21V3c-4 2-5 7-5 11h5"/></>,
  menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
  close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  chevron: <path d="m14 6-6 6 6 6" />,
  'chevron-left': <path d="m14 6-6 6 6 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  sparkles: <><path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z" /><path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6L20 2Z" /></>,
  chat: <><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-5 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" /><path d="M8 10h8M8 13h5" /></>,
  calendar: <><rect x="3.5" y="5" width="17" height="15" rx="3" /><path d="M8 3v4M16 3v4M3.5 10h17" /></>,
  wave: <><path d="M3 8c3 0 3-2 6-2s3 2 6 2 3-2 6-2M3 13c3 0 3-2 6-2s3 2 6 2 3-2 6-2M3 18c3 0 3-2 6-2s3 2 6 2 3-2 6-2" /></>,
  track: <><rect x="3" y="6" width="18" height="12" rx="6" /><rect x="7" y="9.5" width="10" height="5" rx="2.5" /></>,
  trail: <><path d="m3 20 6-11 4 6 3-4 5 9H3Z" /><path d="m9 9 1.5-2.5" /></>,
  tent: <><path d="M12 4 3 20h18L12 4Z" /><path d="m12 20-3-6h6l-3 6Z" /></>,
  send: <><path d="m21 3-7 18-4-7-7-4L21 3Z" /><path d="m10 14 7-7" /></>,
  pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  layers: <><path d="m12 3 10 6-10 6L2 9l10-6Z" /><path d="m3 14 9 5 9-5M3 18l9 5 9-5" /></>,
  activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
  ball: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3v18M5.6 5.6c8 1 8 11.8 12.8 12.8M18.4 5.6c-8 1-8 11.8-12.8 12.8" /></>,
  fitness: <><path d="m7 7 10 10M3 7l4-4M17 21l4-4M3 11l8-8M13 21l8-8" /></>,
  tree: <><path d="m12 3-6 7h3l-5 7h16l-5-7h3l-6-7ZM12 17v5" /></>,
  park: <><path d="M7 3 3 9h2l-3 5h10L9 9h2L7 3ZM7 14v7M13 14h8M13 17h8M14 14v7M20 14v7M2 21h20"/></>,
  'pet-park': <><path d="M6 3 2 9h2l-2 5h8L8 9h2L6 3ZM6 14v7M2 21h20"/><path d="M14 14c-1 1-3 3-2 4s2 0 3 0 2 1 3 0-1-3-2-4c-.5-.5-1.5-.5-2 0Z"/><ellipse cx="12" cy="11.5" rx="1" ry="1.5"/><ellipse cx="15" cy="10" rx="1" ry="1.5"/><ellipse cx="18" cy="11.5" rx="1" ry="1.5"/></>,
  'shared-park': <><path d="M6 3 2 9h2l-2 5h8L8 9h2L6 3ZM6 14v7M2 21h20M16 11v6m-3-3 3-3 3 3M12 17v-6m-3 3 3 3 3-3"/><circle cx="16" cy="6.5" r="2"/></>,
  vet: <><path d="M3 21V6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v15H3ZM10 21v-5h4v5M12 6v6M9 9h6M6 15h1M17 15h1"/><path d="M6 18h1M17 18h1"/></>,
  boarding: <><path d="m3 10 9-7 9 7M5 9v12h14V9M8 21v-7h8v7"/><path d="M9 17h6M9 15v5M15 15v5"/></>,
  'animal-care': <><path d="M12 3 4 6v6c0 4 4 7 8 9 4-2 8-5 8-9V6l-8-3Z"/><path d="M12 7v8M8 11h8"/></>,
  mall: <><path d="M5 8h14l2 13H3L5 8ZM8 9V6a4 4 0 0 1 8 0v3"/><path d="M9.5 16c-1.5.5-2 2-.5 2.5 1 .5 2-.5 3-.5s2 1 3 .5c1.5-.5 1-2-.5-2.5-1-.5-1-1-2-1s-1 .5-2 1Z"/><path d="M9 13h.01M12 12h.01M15 13h.01"/></>,
  directions: <><path d="m12 3 9 9-9 9-9-9 9-9Z"/><path d="M8 16v-5h8m-3-3 3 3-3 3"/></>,
  'menu-book': <><path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1v14"/><path d="M6 9h3M6 12h3M15 9h3M15 12h3"/></>,
  reservation: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18m-12 5 2 2 4-4"/></>,
  phone: <path d="M6 3H3v3c0 8 7 15 15 15h3v-5l-5-2-2 3c-3-1-6-4-7-7l3-2-2-5H6Z"/>,
  globe: <><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 7h14M5 17h14"/></>,
  paw: <><ellipse cx="6" cy="8" rx="2" ry="2.5"/><ellipse cx="10" cy="5" rx="1.8" ry="2.4"/><ellipse cx="15" cy="5" rx="1.8" ry="2.4"/><ellipse cx="19" cy="8" rx="2" ry="2.5"/><path d="M8 13c-2 2-4 5-2 7 2 2 4-1 6-1s4 3 6 1c2-2 0-5-2-7-2-2-6-2-8 0Z"/></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
};

export default function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg aria-hidden="true" focusable="false" data-icon={name} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={style}>{paths[name]}</svg>;
}
