import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type {PetPlace,PetActivity} from './api/client';
import {en,districtsEn,sourceNamesEn} from './locales/en';
export type Language='zh-Hant'|'en';
export const hasChinese=(value:string)=>/[\u3400-\u9fff]/.test(value);
export function translate(key:string,language:Language,values:Record<string,string|number>={}){
  const template=language==='en'?(en[key] ?? key):key;
  return template.replace(/\{(\w+)\}/g,(match,name)=>String(values[name] ?? match));
}
export function formatOpeningHours(value:string,language:Language){
  if(language!=='en')return value;
  const days:Record<string,string>={'星期一':'Monday','星期二':'Tuesday','星期三':'Wednesday','星期四':'Thursday','星期五':'Friday','星期六':'Saturday','星期日':'Sunday','星期天':'Sunday','週一':'Monday','週二':'Tuesday','週三':'Wednesday','週四':'Thursday','週五':'Friday','週六':'Saturday','週日':'Sunday'};
  let result=Object.entries(days).reduce((text,[zh,en])=>text.replaceAll(zh,en),value);
  result=result.replace(/24\s*小時營業|全日營業|全天營業/g,'Open 24 hours').replace(/休息|不營業|公休/g,'Closed').replace(/上午/g,'AM').replace(/下午/g,'PM');
  return result;
}
export function formatActivityDates(value:string,language:Language){
  if(language!=='en')return value;
  const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  let result=value.replace(/(\d{4})年(\d{1,2})月(\d{1,2})日/g,(match,y,m,d)=>Number(m)>=1&&Number(m)<=12?`${d} ${months[Number(m)-1]} ${y}`:match)
    .replace(/(\d{1,2})月(\d{1,2})日/g,(match,m,d)=>Number(m)>=1&&Number(m)<=12?`${d} ${months[Number(m)-1]}`:match)
    .replace(/(上午|下午)\s*(\d{1,2})\s*時\s*至\s*(\d{1,2})\s*時/g,(_,period,start,end)=>`${start}–${end} ${period==='上午'?'AM':'PM'}`)
    .replace(/每日/g,'Daily').replace(/（/g,'(').replace(/）/g,')');
  return formatOpeningHours(result,'en');
}
const categoryKeys: Record<string,string>={restaurants:'狗友善餐廳',parks:'一般公園',pet_parks:'寵物公園',inclusive_parks:'寵物共享公園',vets:'獸醫診所／動物醫院',hotels:'持牌寵物寄養所',transport:'攜寵交通',management:'動物管理／注射中心',malls:'寵物友善商場',activities:'寵物課程',curated:'官方場地補充'};
export function makeLanguage(language:Language,setLanguage:(language:Language)=>void){
  const tx=(value:string,params:Record<string,string|number>={})=>translate(value,language,params);
  const localText=(original:string|null|undefined,english?:string|null)=>{
    if(language!=='en')return original || english || tx('未提供');
    if(english)return english;
    if(!original)return tx('未提供');
    return en[original] || sourceNamesEn[original] || (hasChinese(original)?tx('英文資料未提供'):original);
  };
  const placeName=(p:Pick<PetPlace,'name'|'name_en'> & Partial<Pick<PetPlace,'restaurant_details'>>)=>p.restaurant_details?.display_name || (language==='en'?(p.name_en || p.name):p.name);
  const placeAddress=(p:Pick<PetPlace,'address'|'address_en'>)=>language==='en'?(p.address_en||p.address||tx('來源未有提供地址')):(p.address||p.address_en||tx('來源未有提供地址'));
  const activityName=(a:PetActivity)=>language==='en'?(a.name_en||a.name):a.name;
  const activityDates=(value:string)=>formatActivityDates(value,language);
  const districtName=(value:string|null|undefined)=>value?(language==='en'?(districtsEn[value.replace(/區$/,'')]||value):value):tx('地區未提供');
  const sourceName=(value:string,english?:string|null)=>english && language==='en'?english:language==='en'?(sourceNamesEn[value]||en[value]||(hasChinese(value)?'Official source':value)):value;
  const errorText=(value:string)=>language==='en' && hasChinese(tx(value))?tx('暫時未能完成操作，請稍後再試。'):tx(value);
  const category=(key:string)=>tx(categoryKeys[key]||key);
  const formatTime=(value:string|null|undefined)=>value?new Intl.DateTimeFormat(language==='en'?'en-HK':'zh-HK',{year:'numeric',month:'long',timeZone:'Asia/Hong_Kong'}).format(new Date(value)):tx('未有快照');
  const count=(n:number,kind:'places'|'activities'|'markers'|'results'|'records'|'spots')=>{
    const zh={places:'個地點',activities:'個活動',markers:'個地圖標記',results:'個結果',records:'條',spots:'個名額'};
    const singular={places:'place',activities:'activity',markers:'map pin',results:'result',records:'record',spots:'place'};
    return language==='en'?`${n} ${singular[kind]}${n===1?'':'s'}`:`${n} ${zh[kind]}`;
  };
  return {language,setLanguage,tx,errorText,localText,placeName,placeAddress,activityName,activityDates,districtName,sourceName,category,formatTime,count};
}
const LanguageContext=createContext(makeLanguage('en',()=>{}));
function initialLanguage():Language{
  const param=new URLSearchParams(window.location.search).get('lang');
  if(param==='en'||param==='zh-Hant')return param;
  try{return localStorage.getItem('hkpet.language')==='zh-Hant'?'zh-Hant':'en';}catch{return 'en';}
}
export function LanguageProvider({children}:{children:ReactNode}){
  const [language,setLanguage]=useState<Language>(initialLanguage);
  useEffect(()=>{
    document.documentElement.lang=language==='en'?'en-HK':'zh-HK';
    document.title=language==='en'?'HK PetFinder · Hong Kong Pet Map':'毛孩去邊 · 香港寵物地圖';
    try{localStorage.setItem('hkpet.language',language);}catch{/* Storage may be blocked in private browsing. */}
    const url=new URL(window.location.href);url.searchParams.set('lang',language);window.history.replaceState(null,'',url);
  },[language]);
  const value=useMemo(()=>makeLanguage(language,setLanguage),[language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
export const useLanguage=()=>useContext(LanguageContext);
