# 資料實作備註

來源設定：`backend/app/data/sources.py`。

- 官方獸醫測試樣本：<https://www.pets.gov.hk/tc_chi/animal_health_and_welfare/files/Vet_Clinics_List_20260408.pdf> 第一頁。只用於核實解析器將名稱、地址、電話分欄，唔作醫療推薦。
- `curated_places.json`：少量有官方規則來源嘅商場、碼頭同課程中心。人工核對嘅 ALS 坐標只係建築物代表點，唔係實際入口。
- `cuisine_enrichment.json`：只補充已列入食環署名單、而且同已核實品牌名稱完全匹配嘅餐廳。每筆附品牌菜單／介紹網址；新餐廳可用 `by_licence` 按牌照補充，唔會擴大「准許帶狗」名單。
- SPCA 課程表未公開實時剩餘名額，因此 `remaining=null`。本版冇接入私人報名後台。
- `transport_services.json`：只係官方服務／守則入口，唔提供即時車輛、票價、班次或餘位。
- 餐廳補充資料、菜系及部分照片來自手動保存嘅 Google Places API 回應；設施照片目錄亦有 Google Places 相片快照。呢啲內容唔屬於本項目的 MIT 授權，亦唔係公開資料同步 Worker 即時抓取。
- 底圖使用 OpenFreeMap 的 Positron 樣式，地圖控件顯示 OpenFreeMap、OpenMapTiles 及 OpenStreetMap 的來源標示。

政府／機構名錄同人工補充可能重疊；列表數據唔等於全香港完整設施統計。

- SPCA Pet Care+：https://www.spca.org.hk/animal-care-services/pet-care-courses/pet-care-courses/ 。解析日期、時間、語言、會員／非會員費用、地點、報名連結及 FULL 標記；唔存取報名後台。
- 漁護署活動：https://www.pets.gov.hk/tc_chi/highlights/highlights.html 。從活動連結讀取日期／時間／地點；略過花絮、舊年份同取消公告。唔代表全港活動清單。
- WNP：https://zh.wnp.com.hk/blogs/events 。只讀取活動類標題文章及明確內文日期；單純優惠文章唔當作活動；唔用文章發布時間推算活動年份。

## 專案源碼、授權與第三方內容

- 專案源碼：[GitHub](https://github.com/sammyliao1146-ship-it/hkpetmap)。本項目程式碼採用 [MIT License](../LICENSE)。MIT 授權不涵蓋上游資料、地圖底圖或第三方照片。
- Google Places 照片和地點內容受 [Places API 政策與歸屬要求](https://developers.google.com/maps/documentation/places/web-service/policies)及[Google Maps Platform 條款](https://cloud.google.com/maps-platform/terms)約束。Google 要求顯示照片作者歸屬並提供 Google Maps 原始內容連結；政策亦限制快取／儲存 Places API 內容，以及將 Places 內容用於非 Google 地圖。
- **目前程式碼需要授權審查：**Google Places 相片被保存為本地檔案並由應用程式提供，地點卡片也會出現在 OpenFreeMap 底圖上。加上來源標示不會自動令快取或混用符合 Google 條款；在公開部署前應移除這些本地 Google 相片／Places 內容，或改成符合 Google 條款的來源與地圖整合。
- OpenFreeMap、OpenMapTiles、OpenStreetMap、政府開放資料及機構網站各自保留其來源條款；使用地圖時請保留畫面上的底圖歸屬資訊。官方來源的名錄或照片亦不代表可不受限制地再發布。
