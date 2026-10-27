# HK PetFinder · 毛孩去邊

[繁體中文](./README.md)

A pet-friendly map for Hong Kong. Find dog-friendly restaurants, pet facilities, and activities, with a bilingual interface and an optional AI assistant.

## Project source and license

- Source code: [GitHub](https://github.com/sammyliao1146-ship-it/hkpetmap)
- Software license: [MIT License](./LICENSE)
- Upstream data, basemap tiles, and third-party photos are not covered by this project's MIT license. Follow each provider's terms; see [Data source notes](./docs/DATA_SOURCES.md).

![HK PetFinder map interface](./docs/desktop.png)

## Features

- **Map and search**: Browse restaurants, pet facilities, and activities; filter by district, category, cuisine, or keyword.
- **Pet facilities**: Includes pet parks, inclusive parks, veterinary clinics, licensed pet boarding facilities, animal management and vaccination centres, pet transport, and malls.
- **Activities**: Public course and event information, with dates, locations, fees, or registration links when provided by the source.
- **Bilingual interface**: Switch between Traditional Chinese and English. The language preference is saved in the browser.
- **Optional pet assistant**: Query map data and public information from restricted web domains. It can provide general pet-care information, but not diagnoses or prescriptions.
- **Responsive UI**: Works on desktop and mobile devices.

## Run locally

Requires Python 3.12+, Node.js, and npm. The map can be used without an AI API key.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix frontend ci
cp .env.example .env
bash scripts/dev.sh
```

Open the frontend at <http://127.0.0.1:5174/>. FastAPI documentation is available at <http://127.0.0.1:8001/docs>.

If you already have a `.env`, do not overwrite it with the example. To enable the AI assistant, set a valid `BAI_API_KEY` in `.env`; adjust `BAI_BASE_URL` and `BAI_MODEL` if needed. The key is read only by the backend. The map remains available without valid credentials, but the assistant does not. Web search can be configured with `WEB_SEARCH_*`; blank key/base URL values reuse the `BAI_*` credentials and endpoint.

Redis is optional for the application cache. Without Redis, the app uses an in-process cache, which is not shared between processes. The default shared sync lock requires Redis; use a file lock for single-machine development.

## Data synchronization

The project snapshot is used by the map. The web server reads the snapshot and does not fetch upstream data when visitors open or query the site. Refresh public data manually with:

```bash
.venv/bin/python -m scripts.sync_data --lock file
```

Add `--geocode` to resolve missing addresses. A periodic sync worker can also be started on a single machine:

```bash
.venv/bin/python -m scripts.sync_worker --lock file
```

For deployments across multiple hosts, use a Redis shared lock and run only one sync worker:

```bash
.venv/bin/python -m scripts.sync_worker
```

To start a sync worker alongside the frontend and backend during local development:

```bash
PET_START_SYNC_WORKER=1 PET_SYNC_LOCK_MODE=file bash scripts/dev.sh
```

If a source fetch fails, its last successful data is retained. Places without coordinates are not assigned estimated map locations. The sync interval is this project's refresh policy, not an update-frequency commitment from upstream sources.

See [Data sources](./docs/DATA_SOURCES.md) for source details, parsing methods, and limitations. Official directories and curated additions may overlap, and the listings are not a complete inventory of Hong Kong. General parks may not permit pets, and restaurant policies can vary by location. Confirm current rules with the venue or service provider before visiting.

## API

All API paths are prefixed with `/api/v1`:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `GET` | `/catalog` | Categories, cuisines, and source status |
| `GET` | `/places` | Search restaurants or facilities |
| `GET` | `/places/{place_id}` | Place details |
| `GET` | `/activities` | Search activities |
| `GET` | `/assistant/capabilities` | Assistant capabilities and tools |
| `POST` | `/assistant/chat` | Assistant chat |
| `POST` | `/assistant/chat/stream` | Streaming assistant chat (SSE) |

See the local FastAPI documentation for filter parameters and request/response formats: <http://127.0.0.1:8001/docs>.

The assistant uses read-only data tools and supports function tools or a local MCP stdio transport. It does not support bookings, payments, login, route or travel-time estimates, or unrestricted web search. Pet-health responses are for general care information and triage only, not diagnosis, prescriptions, or medication dosages.

Start the MCP stdio server with:

```bash
.venv/bin/python -m agent.data.mcp_server
```

## Development and checks

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend run build
npm --prefix frontend run check:i18n
npm --prefix frontend run check:language
```

Tests cover the API, source parsers, snapshot synchronization, and Agent tools. See [docs/DATA_SOURCES.md](./docs/DATA_SOURCES.md) for public-source samples and data-use notes.
