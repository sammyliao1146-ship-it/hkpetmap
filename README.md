# 毛孩去邊 · HK PetFinder

[English](./README.en.md)

香港寵物友善地圖，集中搜尋狗友善餐廳、寵物設施及活動，並提供中英雙語介面和可選的 AI 助手。

## 專案源碼與授權

- 專案源碼：[GitHub](https://github.com/sammyliao1146-ship-it/hkpetmap)
- 程式碼授權：[MIT License](./LICENSE)
- 上游資料、地圖底圖和第三方照片不屬於本項目的 MIT 授權；請按各來源條款使用，詳見[資料來源說明](./docs/DATA_SOURCES.md)。

![毛孩去邊地圖介面](./docs/desktop.png)

## 功能

- **地圖及搜尋**：瀏覽餐廳、寵物設施和活動；按地區、分類、菜系或關鍵字篩選。
- **寵物設施**：包括寵物公園、共享公園、獸醫診所、持牌寄養所、動物管理／注射中心、攜寵交通及商場。
- **活動資訊**：整合公開課程和活動資料，提供日期、地點、費用或報名來源（視乎來源有否提供）。
- **中英雙語**：可在繁體中文和英文之間切換；語言設定會保存在瀏覽器。
- **寵物助手（可選）**：可查詢地圖資料和受限網域的公開資訊；支援一般寵物照護資訊，不提供診斷或處方。
- **響應式介面**：支援桌面和流動裝置。

## 本機啟動

需要 Python 3.12+、Node.js／npm。基本地圖可在沒有 AI API key 的情況下使用。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix frontend ci
cp .env.example .env
bash scripts/dev.sh
```

開啟前端 <http://127.0.0.1:5174/>；FastAPI 文件位於 <http://127.0.0.1:8001/docs>。

如已有 `.env`，請勿用範例覆蓋。要使用 AI 助手，請在 `.env` 設定有效的 `BAI_API_KEY`；需要時亦可調整 `BAI_BASE_URL` 和 `BAI_MODEL`。密鑰只由後端讀取。未設定有效憑證時，地圖仍可使用，但助手不可用。Web 搜尋可使用 `WEB_SEARCH_*` 設定；留空的 key／base URL 會沿用 `BAI_*` 憑證和端點。

Redis 為可選快取。沒有 Redis 時，應用程式會使用程序內快取；多個程序不會共享該快取。共享同步鎖預設需要 Redis；單機開發可改用檔案鎖。

## 資料同步

專案提供的快照會供地圖使用。Web 伺服器只讀快照，不會因訪客開頁或查詢而抓取上游資料。需要更新公開資料時，可手動執行：

```bash
.venv/bin/python -m scripts.sync_data --lock file
```

需要解析缺少的地址時，可加上 `--geocode`。單機亦可啟動定時同步 Worker：

```bash
.venv/bin/python -m scripts.sync_worker --lock file
```

正式環境如有多個主機，請使用 Redis 共享鎖，並只運行一個同步 Worker：

```bash
.venv/bin/python -m scripts.sync_worker
```

本機開發若要與前後端一同啟動同步 Worker：

```bash
PET_START_SYNC_WORKER=1 PET_SYNC_LOCK_MODE=file bash scripts/dev.sh
```

來源抓取失敗時會保留該來源上次成功的資料；缺少坐標的地點不會被放到估算位置。同步週期是本專案的更新策略，不代表上游來源承諾的更新頻率。

資料來源、解析方式和限制詳見[資料來源說明](./docs/DATA_SOURCES.md)。官方名錄及人工補充資料可能重疊，列表不代表全港完整統計；一般公園不一定准許攜寵，餐廳的准入條件亦可能因店舖而異。使用前請向場地或服務提供者確認最新規則。

## API

所有 API 路徑以 `/api/v1` 為前綴：

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 健康檢查 |
| `GET` | `/catalog` | 分類、菜系及來源狀態 |
| `GET` | `/places` | 搜尋餐廳或設施 |
| `GET` | `/places/{place_id}` | 場地詳情 |
| `GET` | `/activities` | 搜尋活動 |
| `GET` | `/assistant/capabilities` | 助手能力及工具資訊 |
| `POST` | `/assistant/chat` | 助手對話 |
| `POST` | `/assistant/chat/stream` | 串流助手對話（SSE） |

篩選參數和請求／回應格式可在本機 FastAPI 文件中查看：<http://127.0.0.1:8001/docs>。

助手使用唯讀資料工具；可透過 function tools 或本機 MCP stdio 傳輸。它不提供預訂、付款、登入、路線或行程時間估算，也不允許任意網域搜尋。寵物健康內容僅供一般照護及就醫分流參考，不作診斷、處方或用藥劑量建議。

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

測試涵蓋 API、資料來源解析、快照同步及 Agent 工具。官方來源樣本和資料使用注意事項見 [docs/DATA_SOURCES.md](./docs/DATA_SOURCES.md)。
