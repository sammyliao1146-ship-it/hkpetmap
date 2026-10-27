"""English companions for application-authored guidance; never translate unknown source text by guesswork."""
from backend.app.data.google_cuisines import EXTRA_CUISINES

CATEGORY_EN = {'restaurants':'Dog-friendly restaurants','parks':'General parks','pet_parks':'Pet parks','inclusive_parks':'Inclusive parks for pets','vets':'Veterinary clinics / Hospitals','hotels':'Licensed pet boarding','transport':'Pet transport','management':'Animal management / Vaccination','malls':'Pet-friendly malls'}
CUISINE_EN = {'咖啡／輕食':'Coffee / Light meals','中式':'Chinese','港式':'Hong Kong style','日式':'Japanese','韓式':'Korean','西式':'Western','意式／薄餅':'Italian / Pizza','泰式':'Thai','越式':'Vietnamese','甜品':'Desserts','素食':'Vegetarian','未分類':'Unclassified', **EXTRA_CUISINES}
SOURCE_EN = {'康文署／CSDI':'LCSD / CSDI','漁護署／CSDI':'AFCD / CSDI','食環署：獲准許狗隻進入嘅食肆名單':'FEHD: Premises permitted to admit dogs','漁護署持牌動物寄養所名單':'AFCD licensed animal boarding list','漁護署獸醫診所名單':'AFCD veterinary clinic list','AIRSIDE 官方寵物友善指引':'AIRSIDE official pet-access guide','SPCA 官方課程及場地資料':'SPCA official course and venue information','新渡輪官方攜寵守則':'Sun Ferry official pet-carriage rules','香港愛護動物協會 SPCA':'SPCA (Hong Kong)'}
NOTES_EN = {
 '一般公園資料唔代表准許帶寵物，出發前請核實場內告示。':'A general park listing does not confirm pet access. Check the venue notices before visiting.',
 '只限指定範圍；請遵守牽繩及場地守則。':'Access is limited to designated areas. Follow leash requirements and venue rules.',
 '准許狗隻進入唔代表接受其他寵物，入場條件以餐廳守則為準。':'Permission to admit dogs does not cover other pets. Check the restaurant’s access rules.',
 '只包括同意公開資料嘅持牌寄養所，唔係全港完整名單。':'Only licensed boarding establishments that agreed to be listed are included. This is not a complete Hong Kong directory.',
 '價格、可接待動物同房位請直接向寄養所查詢。':'Ask the boarding establishment about prices, accepted animals and availability.',
 '自願列入嘅診所名錄，唔係醫院牌照認證。':'This is a voluntary clinic directory, not a hospital licensing certification.',
 '急症服務、營業時間同接受動物種類請先致電核實。':'Call to confirm emergency services, opening hours and accepted animal species.',
 '寵物共融區：地下露天廣場、地下商場室內空間、2樓空中農莊同6樓空中花園。':'Pet-friendly zones: the ground-floor plaza and indoor mall area, AIR Farm on 2/F and AIRSIDE Garden on 6/F.',
 '請牽繩，個別商店同餐廳規則另計。':'Keep pets on a leash. Individual shops and restaurants have their own rules.',
 '訓練課程喺2樓平台舉行，實際上課位置以課程通知為準。':'Training takes place on the 2/F terrace. Check your course notice for the exact meeting point.',
 '醫療服務同開放時間請向中心核實。':'Check medical services and opening hours directly with the centre.',
 '提供狗隻訓練課程，上課安排請睇課程通知。':'Dog training courses are offered here. Check the course notice for attendance arrangements.',
 '往長洲航線有攜寵安排；普通渡輪豪華位唔接受寵物。':'Pet carriage is available on the Cheung Chau route. Pets are not permitted in deluxe class on ordinary ferries.',
 '按守則使用籠／袋／寵物車，或牽繩並戴口罩；上船前請向職員確認。':'Use a suitable cage, carrier or pet stroller, or a leash and muzzle, in accordance with the rules. Confirm with staff before boarding.',
 '往梅窩航線有攜寵安排，班次同指定座位請向營辦商確認。':'Pet carriage is available on the Mui Wo route. Confirm sailings and designated seating with the operator.',
 '按守則使用籠／袋／寵物車，或牽繩並戴口罩。':'Use a suitable cage, carrier or pet stroller, or a leash and muzzle, in accordance with the rules.',
}
CURATED_EN = {
 'curated:airside':('AIRSIDE',None),
 'curated:spca-wan-chai':('SPCA Wan Chai Centre',None),
 'curated:spca-tsing-yi':('SPCA Tsing Yi Centre',None),
 'curated:central-pier-5':('Central Pier 5 · Cheung Chau route',None),
 'curated:central-pier-6':('Central Pier 6 · Mui Wo route',None),
}


def enrich_english(places,activities):
    for p in places:
        if not p.source_name_en:
            p.source_name_en=SOURCE_EN.get(p.source_name)
        if p.id in CURATED_EN and not p.name_en:
            p.name_en=CURATED_EN[p.id][0]
        # Source-provided English notes are retained, alongside translated app guidance.
        p.notes_en=list(dict.fromkeys([*p.notes_en,*(NOTES_EN[n] for n in p.notes if n in NOTES_EN)]))
    for a in activities:
        if not a.source_name_en:
            a.source_name_en=SOURCE_EN.get(a.source_name)
        if not a.fee_text_en and a.fee_text:
            candidate=a.fee_text.replace('非會員：','Non-member: ').replace('會員：','Member: ').replace('免費','Free')
            if not any('\u3400'<=c<='\u9fff' for c in candidate):
                a.fee_text_en=candidate
        if not a.language_en and a.language:
            a.language_en={'英語':'English','中文':'Chinese','中文及英語':'Chinese and English'}.get(a.language)
        if not a.venue_name_en and a.venue_name and not any('\u3400'<=c<='\u9fff' for c in a.venue_name):
            a.venue_name_en=a.venue_name
        if not a.description_en and a.description.startswith('SPCA ') and a.description.endswith('完整課程內容同入學條件請睇主辦方頁面。'):
            a.description_en=f'SPCA {a.name_en or "dog training course"}. See the organiser’s page for full course details and entry requirements.'
        if not a.eligibility_en and a.eligibility=='疫苗紀錄、年齡同體型要求，以主辦方個別課程為準。':
            a.eligibility_en='Vaccination records, age and size requirements depend on the individual course. Check with the organiser.'
