"""Whole-message grammars for deterministic saved-data answers, never keyword scope bypasses."""
import re

from agent.data.data_access import TRANSPORT_RULES
from agent.data.saved_lookup import saved_lookup
from agent.subagents.intent_router import assistant_intro_reply, gate_reply
from backend.app.data.geography import DISTRICTS

ZH_DISTRICTS='|'.join(sorted(set(DISTRICTS.values())|{'港島','香港島','九龍','新界'},key=len,reverse=True))


def _name(p, language):
    return (p.get('name_en') or p['name']) if language=='en' else ((p.get('restaurant_details') or {}).get('display_name') or p['name'])


async def fast_answer(message, history, access, language):
    text=message.strip().rstrip('.?？。').strip()
    # A request for the application's credentials is always refused locally;
    # a classifier outage must not turn it into a provider error or disclosure.
    if re.search(r'(?:reveal|show|print|give me|tell me|洩露|泄露|顯示|显示|告訴我|告诉我).{0,80}(?:your|server|system|你|系統|系统).{0,40}(?:api[ _-]?key|database password|system prompt|密鑰|密钥|資料庫密碼|数据库密码)',text,re.I):
        return {'answer':('I cannot disclose application credentials, database passwords or private system instructions.' if language=='en' else '我唔會提供應用程式密鑰、資料庫密碼或內部系統指令。'),
                'routing':{'intent':'out_of_scope','map_mode':'none','confidence':1,'action':'refuse','classifier_model':'local-security-rule'}}
    # Denial-only rule: it can refuse disclosure but can never authorise a query.
    if re.search(r'\b(?:reveal|show|print|expose)\b.{0,100}\b(?:api keys?|database passwords?|system prompts?|private keys?|access tokens?)\b',text,re.I) or re.search(r'(?:洩露|泄露|顯示|显示|輸出|输出|告訴我|告诉我).{0,60}(?:API.{0,2}(?:密鑰|密钥)|資料庫密碼|数据库密码|系統提示詞|系统提示词)',text,re.I):
        return {'answer':gate_reply('refuse',language),'routing':{'intent':'out_of_scope','map_mode':'none',
                'confidence':1,'action':'refuse','classifier_model':'local-denial-rule'}}
    direct=saved_lookup(text,history,access,language)
    if direct:return direct
    if re.fullmatch(r'(?:show me|find) dog training courses(?:, with dates, venues, fees and enrolment links)?|幫我睇吓有咩狗隻訓練班(?:，列出日期、地點、費用同報名連結)?',text,re.I):
        data=await access.search_activities(category='訓練課程',limit=3)
        rows=data['items'];lines=[]
        for row in rows:
            name=(row.get('name_en') or row['name']) if language=='en' else row['name']
            venue=(row.get('venue_name_en') or row.get('venue_name')) if language=='en' else row.get('venue_name')
            fee=(row.get('fee_text_en') or row.get('fee_text')) if language=='en' else row.get('fee_text')
            unknown='Not published' if language=='en' else '未有公布'
            lines.append(f"- **{name}** · {row.get('dates_text') or unknown}\n  {venue or unknown} · {fee or unknown}\n  [{'Listing / enrolment' if language=='en' else '原文／報名'}]({row.get('booking_url') or row['source_url']})")
        answer='\n'.join(lines) if lines else ('No saved dog-training courses are listed.' if language=='en' else '暫未有已收錄狗隻訓練課程。')
        answer+='\n\n'+('Published listings only; confirm dates, fees and remaining places with the organiser. No booking was made.' if language=='en' else '以上係已公布課程資料；日期、費用及剩餘名額請向主辦方確認，未有代你報名。')
        return {'answer':answer,'sources':list({r['source_url']:{'title':r.get('source_name',''),'url':r['source_url']} for r in rows}.values())}
    if re.fullmatch(r'(?:我(?:星期[一二三四五六日天])?想帶狗出街[，,])?有咩攜寵交通服務(?:[？?]有咩條件要留意)?|(?:i want to take my dog out on (?:sunday|saturday)\. )?what pet transport options and rules should i know about',text,re.I):
        services=access.pets.catalogue()['transport_services']
        lines=[];sources=[]
        for s in services:
            name=(s.get('name_en') or s['name']) if language=='en' else s['name']
            notes=(s.get('notes_en') or s.get('notes')) if language=='en' else s.get('notes')
            lines.append(f"- **{name}**: {notes or ''}");sources.append({'title':name,'url':str(s['url'])})
        lines.extend(r['notes_en'] if language=='en' else r['notes'] for r in TRANSPORT_RULES)
        sources.extend({'title':r['mode'],'url':r['source_url']} for r in TRANSPORT_RULES)
        answer='\n\n'.join(lines)+'\n\n'+('Saved guidance only; confirm the selected date, service availability, tickets and rules with each operator.' if language=='en' else '以上係已收錄指引；所選日期嘅實際班次、供應、車票及最新規則請向營辦商確認。')
        return {'answer':answer,'sources':sources}
    if re.fullmatch(r'who are you|what can you do|你係邊個|你是誰|你能做什麼|你可以做咩',text,re.I):
        return {'answer':assistant_intro_reply(language)}
    if re.fullmatch(r'how to go to (?:the )?restaurant|how do i get (?:there|to the restaurant)|點去(?:嗰間|呢間)?餐廳|點去',text,re.I):
        recent=access.recent_places(history)
        if len(recent)!=1:
            if history and not recent:return None
            return {'answer':'Which restaurant do you mean? Please give its name or select it on the map.' if language=='en' else '你想去邊間餐廳？請提供名稱或喺地圖揀選。'}
        data=await access.directions(recent[0]['id'])
        # Navigation URL construction is still delegated to the existing validated tool.
        links=data.get('directions') or []
        if not links:return None
        answer='\n'.join(f"- [{link['mode'].title() if language=='en' else {'walking':'步行導航','driving':'駕車導航'}[link['mode']]}]({link['url']})" for link in links)
        answer+='\n\n'+('These are external navigation links, not verified pet-accessible routes or travel times.' if language=='en' else '以上係外部導航連結，未核實沿途攜寵通道，亦未提供行程時間。')
        return {'answer':answer,'places':[{'id':data['place']['id'],'name':_name(data['place'],language)}], 'sources':access.direction_sources}
    if re.fullmatch(r'can i (?:take|bring) my (?:dog|cat|pet) on (?:ordinary )?(?:the )?mtr(?: and minibuses)?|can i (?:take|bring) my (?:dog|cat|pet) on minibuses|狗(?:狗)?可以搭(?:港鐵|小巴)(?:同小巴)?嗎|可以帶狗搭(?:港鐵|小巴)嗎',text,re.I):
        rules=TRANSPORT_RULES
        answer='\n\n'.join(r['notes_en'] if language=='en' else r['notes'] for r in rules)
        answer+='\n\n'+('Saved transport guidance; check the official sources for current arrangements.' if language=='en' else '以上係已收錄交通指引，最新安排請核對官方來源。')
        return {'answer':answer,'sources':[{'title':r['mode'],'url':r['source_url']} for r in rules]}
    mall=re.fullmatch(r'does (.+) require my (?:dog|cat|pet) to stay in a (?:pet )?(?:stroller|carrier)',text,re.I)
    if mall:
        target=mall.group(1).strip().casefold()
        matches=[p for p in (access.pets.snapshot.places if access.pets.snapshot else []) if p.category=='malls'
                 and target in {n.casefold() for n in (p.name,p.name_en) if n}]
        if len(matches)==1:
            p=matches[0];notes=(p.notes_en if language=='en' else p.notes) or p.notes
            if notes:
                answer='\n'.join(notes[:6])+'\n\n'+('Saved venue guidance, not a fresh check. Confirm current rules and individual tenant restrictions with the mall.' if language=='en' else '以上係已收錄場地指引，並非即時查證；最新安排及個別店舖規則請向商場確認。')
                return {'answer':answer,'places':[{'id':p.id,'name':p.name_en or p.name}],
                        'sources':[{'title':p.source_name,'url':str(p.source_url)}]}
    cuisine=None;region=None;district='';rating=None;price=None;limit=3
    cuisines={'japanese':'日式','italian':'意式／薄餅','korean':'韓式','thai':'泰式','chinese':'中式'}
    match=re.fullmatch(r'find ([1-5]) dog-friendly (Japanese|Italian|Korean|Thai|Chinese) restaurants in (Kowloon|Hong Kong Island|New Territories) rated at least ([0-5](?:\.\d)?)',text,re.I)
    cafe=re.fullmatch(r'(?:find|show me) dog-friendly caf[eé]s in ([A-Za-z -]+)(?:, with source links)?',text,re.I)
    zh_cafe=re.fullmatch(r'(?:我想)?(?:帶狗)?去('+ZH_DISTRICTS+r')(?:區)?(?:飲|喝)咖啡(?:[，,](?:幫我)?(?:搵|找)(?:有資料來源(?:嘅|的))?餐廳)?',text)
    if cafe or zh_cafe:
        district=(cafe or zh_cafe).group(1)
        if cafe and district.lower() not in DISTRICTS:return None
        cuisine='咖啡／輕食'
    elif match:
        count,cuisine,region,rating=match.groups();limit=int(count);cuisine=cuisines[cuisine.lower()]
        region={'kowloon':'kowloon','hong kong island':'hong_kong_island','new territories':'new_territories'}[region.lower()];rating=float(rating)
        if rating>5:return None
    else:
        match=re.fullmatch(r'find dog-friendly restaurants under (?:HK\$|\$)?([1-9]\d{0,4}) per person',text,re.I)
        if not match:return None
        price=float(match.group(1))
    result=await access.search_places(mode='restaurants',cuisine=cuisine or '',district=region or district,
                                     sort_by='rating' if rating is not None else 'default',min_rating=rating,
                                     max_price=price,limit=limit,exclude_review_candidates=True)
    rows=result['items']
    if not rows:
        answer='No saved restaurants match all those filters. Missing ratings/prices are not treated as a match.' if language=='en' else '暫未有已儲存餐廳符合全部條件；缺少評分或價錢嘅餐廳唔會當作符合。'
    else:
        lines=[]
        for p in rows:
            d=p.get('restaurant_details') or {};rating_text=f" · ★ {d['rating']}" if d.get('rating') is not None else ''
            address=(p.get('address_en') or p.get('address') or '') if language=='en' else (p.get('address') or '')
            lines.append(f"- **{_name(p,language)}**{rating_text}\n  {address}")
        answer='\n'.join(lines)
    answer+='\n\n'+('Saved Google ratings/prices and published dog-access listings, not live verification. Confirm hours, menus and access rules with the venue.' if language=='en' else '按已儲存 Google 評分／價錢及已公布攜狗名單篩選，並非即時核實；營業時間、餐牌和入場規則請向餐廳確認。')
    return {'answer':answer,'places':[{'id':p['id'],'name':_name(p,language)} for p in rows],
            'sources':list({p['source_url']:{'url':p['source_url'],'title':p.get('source_name','')} for p in rows if p.get('source_url')}.values())}
