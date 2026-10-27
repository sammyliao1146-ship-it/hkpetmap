# 毛孩去邊 · HK PetFinder

[English](./README.en.md)

**線上網站：<https://hkpetmap.com>**（目前正在運行）

香港寵物友善地圖，集中搜尋狗友善餐廳、寵物設施及活動，提供中英雙語介面、行程規劃和可選的 AI 寵物助手。

![毛孩去邊地圖介面](./docs/desktop.png)

## 目錄

- [功能](#功能)
- [架構](#架構)
- [本機啟動](#本機啟動)
- [設定](#設定)
- [資料同步](#資料同步)
- [API](#api)
- [AI 助手](#ai-助手)
- [開發與檢查](#開發與檢查)
- [授權與資料來源](#授權與資料來源)

## 功能

- **地圖及搜尋**：瀏覽餐廳、寵物設施和活動；按地區、分類、菜系或關鍵字篩選。
- **寵物設施**：寵物公園、共享公園、獸醫診所、持牌寄養所、動物管理／注射中心、攜寵交通及商場。
- **活動資訊**：整合公開課程和活動資料，提供日期、地點、費用或報名來源（視乎來源有否提供）。
- **停車場**：附近政府停車場資料及空位（來源為 DATA.GOV.HK，僅供參考，非預訂保證）。
- **行程規劃**：按日期、地區和興趣（公園、獸醫、活動、商場、餐廳）生成行程，並把每個地點分配到 1,000 米內的真實停車場。詳見 [docs/OUTING_PLAN.md](./docs/OUTING_PLAN.md)。
- **中英雙語**：繁體中文和英文切換；語言設定保存在瀏覽器。新訪客預設英文，亦可用 `?lang=zh-Hant`。
- **寵物助手（可選）**：查詢地圖資料和受限網域的公開資訊；提供一般寵物照護資訊，不作診斷或處方。
- **響應式介面**：支援桌面和流動裝置。

## 架構

| 目錄 | 內容 |
| --- | --- |
| `frontend/` | 前端（Vite + TypeScript） |
| `backend/app/` | FastAPI 後端：路由、服務、快取、設定、資料適配器 |
| `agent/data/` | 數據接口：地圖資料存取、搜尋、附近餐廳回答、工具函式及本機 MCP 伺服器 |
| `agent/assembly/` | 主 agent 組裝：提示詞、模型客戶端池、`run_pet_assistant` |
| `agent/memory/` | 對話記憶（短期、按 `session_id` 快取） |
| `agent/subagents/` | 子 agent：意圖分類、回答審核、受限網頁研究、行程選點 |
| `scripts/` | 開發啟動、資料同步及照片處理腳本 |
| `data/` | 資料快照 |
| `docs/` | 文件及截圖 |

Web 伺服器只讀取已發佈的資料快照；上游資料由獨立同步程序更新。

## 本機啟動

需要 Python 3.12+、Node.js／npm。基本地圖無需 AI API key。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix frontend ci
cp .env.example .env
bash scripts/dev.sh
```

前端：<http://127.0.0.1:5174/>；FastAPI 文件：<http://127.0.0.1:8001/docs>。

如已有 `.env`，請勿用範例覆蓋。

## 設定

設定經 `.env` 提供（見 [.env.example](./.env.example)）。密鑰只由後端讀取。

| 變數 | 用途 |
| --- | --- |
| `BAI_API_KEY` / `BAI_BASE_URL` / `BAI_MODEL` | 主助手模型憑證和端點；未設定有效憑證時地圖仍可用，助手不可用 |
| `MAIN_REASONING_EFFORT` | 主助手推理強度，留空則不傳此參數 |
| `INTENT_MODEL` / `INTENT_CONFIDENCE_THRESHOLD` / `INTENT_TIMEOUT_SECONDS` | 意圖分類（無降級；失敗即拒絕） |
| `WEB_SEARCH_*` | 網頁研究子 agent；留空的 key／base URL 沿用 `BAI_*` |
| `AGENT_TOOL_TRANSPORT` | 工具傳輸：`function`（預設）或 `mcp_stdio` |
| `CHAT_RATE_LIMIT` / `CHAT_RATE_HARD_LIMIT` / `CHAT_RATE_WINDOW_SECONDS` | 對話限流：超過軟上限改用 `FALLBACK_MODEL`，超過硬上限回 429 |
| `LLM_MAX_CONCURRENCY` / `LLM_FALLBACK_CONCURRENCY` / `LLM_QUEUE_TIMEOUT_SECONDS` | 每程序模型併發上限及排隊逾時 |
| `REDIS_URL` / `CACHE_PREFIX` | 可選 Redis 快取 |
| `CORS_ORIGINS` | 允許的來源；API 另外預設接受 `https://hkpetmap.com` 及 `https://www.hkpetmap.com` |
| `PET_SNAPSHOT_PATH` / `SNAPSHOT_POLL_SECONDS` / `SYNC_CHECK_SECONDS` / `SNAPSHOT_MAX_AGE_SECONDS` | 快照位置、輪詢及同步週期 |

沒有 Redis 時會使用程序內快取（多程序不共享）。共享同步鎖預設需要 Redis；單機開發可改用檔案鎖。

## 資料同步

Web 伺服器不會因訪客開頁或查詢而抓取上游資料。需要更新時：

```bash
.venv/bin/python -m scripts.sync_data --lock file
```

需要解析缺少的地址時，加上 `--geocode`。單機可啟動定時同步 Worker：

```bash
.venv/bin/python -m scripts.sync_worker --lock file
```

多主機正式環境請使用 Redis 共享鎖，並只運行一個 Worker：

```bash
.venv/bin/python -m scripts.sync_worker
```

本機開發若要與前後端一同啟動 Worker：

```bash
PET_START_SYNC_WORKER=1 PET_SYNC_LOCK_MODE=file bash scripts/dev.sh
```

來源抓取失敗時保留該來源上次成功的資料；缺少坐標的地點不會被放到估算位置。同步週期是本專案的更新策略，不代表上游來源承諾的更新頻率。

## API

所有路徑以 `/api/v1` 為前綴；線上文件可於本機 `/docs` 查看。

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 健康檢查 |
| `GET` | `/catalog` | 分類、菜系及來源狀態 |
| `GET` | `/places` | 搜尋餐廳或設施 |
| `GET` | `/places/{place_id}` | 場地詳情 |
| `GET` | `/activities` | 搜尋活動 |
| `GET` | `/parking` | 附近停車場及空位 |
| `GET` | `/plans/options` | 行程規劃可選地區及目的地 |
| `POST` | `/plans` | 生成行程 |
| `GET` | `/assistant/capabilities` | 助手能力及工具資訊 |
| `POST` | `/assistant/prefill` | 分享位置後預熱附近餐廳回答 |
| `POST` | `/assistant/chat` | 助手對話 |
| `POST` | `/assistant/chat/stream` | 串流助手對話（SSE） |

另有餐廳／設施照片端點（`/restaurant-photos/…`、`/facility-photos/…`、`/restaurant-dish-photos/…`）。對話及行程端點設有限流。

## AI 助手

對話請求依次經過：

1. **意圖分類**（`subagents/intent_router`）：判斷意圖及信心；越界請求拒絕，低信心則要求澄清，分類失敗一律不放行。
2. **路由**：身份問題直接回答；網頁研究走受限 sub-agent；其餘交給主 agent。
3. **主 agent**（`assembly/service`）：使用唯讀資料工具（function tools 或本機 MCP stdio）及網頁研究工具；支援串流輸出。
4. **回答審核**（`subagents/answer_guard`）：檢查切題、範圍和是否回應當前請求，失敗即不回傳。
5. **記憶**（`memory/conversation`）：帶 `session_id` 時保存最近 5 則訊息，10 分鐘過期。

模型併發有上限，超出時降級至輕量模型；仍滿載則回 503。網頁研究只搜尋限定網域並驗證引用來源。助手不提供預訂、付款、登入、路線或行程時間估算，也不允許任意網域搜尋。寵物健康內容僅供一般照護及就醫分流參考，不作診斷、處方或用藥劑量建議。

啟動 MCP stdio 伺服器：

```bash
.venv/bin/python -m agent.data.mcp_server
```

## 開發與檢查

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend run check:i18n
npm --prefix frontend run check:language
```

測試涵蓋 API、資料來源解析、快照同步、行程規劃及 Agent 鏈路（意圖路由、審核、網頁研究、限流降級）。

## 授權與資料來源

- 源碼：[GitHub](https://github.com/sammyliao1146-ship-it/hkpetmap)；程式碼授權：[MIT License](./LICENSE)。
- 上游資料、地圖底圖和第三方照片不屬於本項目的 MIT 授權，請按各來源條款使用，詳見[資料來源說明](./docs/DATA_SOURCES.md)。
- 官方名錄及人工補充資料可能重疊，列表不代表全港完整統計；一般公園不一定准許攜寵，餐廳的准入條件亦可能因店舖而異。使用前請向場地或服務提供者確認最新規則。
