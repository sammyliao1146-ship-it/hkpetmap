# Pet outings, Explore and parking

The main navigation contains Restaurants, Plan and Explore. Explore combines facilities and activities. Inclusive parks appear under General parks without changing their stored access policies. Exercise amenities are nested under Pet parks. Opening Activities, selecting an activity category or selecting Refresh requests the activity snapshot once; activities are not polled.

New visitors see English. Explicit `?lang=zh-Hant` and saved language choices are respected. The API accepts the `https://hkpetmap.com` and `https://www.hkpetmap.com` CORS origins alongside configured development origins.

## Parking

`GET /api/v1/parking?language=en` returns government car park data in a shape compatible with map places. Optional `latitude`, `longitude`, `radius_m` and `limit` filter nearby car parks. Supply both coordinates together.

The source is [DATA.GOV.HK parking information and vacancy](https://data.gov.hk/en-data/dataset/hk-dpo-datagovhk1-carpark-info-vacancy). Basic bilingual information is cached for 24 hours; vacancy responses for 60 seconds. Vacancy older than 15 minutes is marked stale. Failed upstream requests use the last available Redis or disk snapshot and a short retry backoff. Prices, height limits and availability remain source data, not booking guarantees.

## Plan

`GET /api/v1/plans/options` lists supported regions and source-backed random destinations.

`POST /api/v1/plans` accepts:

```json
{
  "date": "2026-10-27",
  "region": "hong_kong_island",
  "interests": ["park", "mall"],
  "cuisine": "日式",
  "random": false,
  "language": "en"
}
```

Regions are `any`, `hong_kong_island`, `kowloon` and `new_territories`. An optional `district` preserves an explicitly requested district. Interests are `park`, `vet`, `activity` and `mall`; an empty list requests a meal-only plan. Empty cuisine means any cuisine and still includes a food stop when available. `destination_id` can explicitly select an option; an optional `origin` contains `latitude` and `longitude`.

Plan uses the same complete cuisine catalogue as the Restaurants Flavour filter, including Unclassified. Sushi is grouped under Japanese; legacy `sushi` requests are mapped to the same Japanese category. No Google API request is made during planning.

Ordinary planning considers local venues within the selected region. Random planning uses the previously discussed waterfront and park destinations, filtered by region. Locations come from existing source-backed records; a named destination is not proof that every sub-area has been imported. In particular, the Science Park anchor can come from another saved venue within the park and is not a verified Furtopia entrance.

The backend builds candidate IDs and their eligible car parks. A balanced shortlist of at most six candidates per requested module is passed directly as data to the Agents SDK planner. One model turn returns only selected stop IDs; there is no candidate-fetch tool round trip. The backend rejects unknown IDs, removes duplicates, fills missing requested modules when eligible records exist, and groups stops around real car parks. Every included stop must be at most 1,000 metres from its assigned car park. More than one parking group is returned when needed. Missing modules produce a partial result instead of invented places.

If a single car park can cover candidates for all available requested modules, the backend restricts the agent to that car park's coverage before selection. This prevents avoidable parking moves. Food is the last stop; a plan includes at most one restaurant.

The structured response contains `parking_groups`, `map_places`, `summary`, `warnings` and `sources`. Only mall stops have `mall_policy_summary`; other venue policies remain available in their ordinary detail popups. Circles represent straight-line radius, not verified pedestrian routes. External Maps links handle actual navigation; the planner does not invent travel times.

## Chat planning and latency

Supported chat itineraries share the same validated planner. Complete context-free commands such as `give me a random plan` or `give me a plan that includes restaurant shopping mall` are recognised by whole-message rules, then use one selection model call. Extra words/constraints or history disable these rules. Other chat messages use the existing classifier to extract intent and typed planning preferences in the same call, then use one selection call. User date, region, district, interests, cuisine, area and random choice are retained. Unspecified dates use today's Hong Kong date with an explicit note; opening hours remain unverified.

Budget, rating thresholds, exact times, named specific venues, fresh web checks and other unrepresented conditions retain the general Agent path. Unknown district/cuisine values do the same; they are never silently discarded. The structured result is rendered from validated records and a template, so it needs no additional free-text generation or model relevance review. General Agent and web answers retain their existing checks. Private traces record the selected planning route and preferences.

Prepared candidate IDs/geometry use a ten-minute L1/Redis cache bounded to 512 entries / 8 MiB per process. Keys include the saved-data revision, complete planning preferences and exact origin, plus parking location IDs/coordinates. Cached entries omit photos, reviews, vacancy and full place facts. Current records are rehydrated on every request; parking geometry or snapshot changes invalidate candidates, and random area selection runs again after the cache read. Final itineraries and conversation replies are not cached here.

Planning reads parking snapshots without upstream refresh. A bundled government location catalogue (575 car parks, bilingual names/addresses and saved coordinates) supports cold deployments; it contains no vacancy values, prices or height-limit claims. The existing parking API can refresh source data on demand. The dedicated `scripts.sync_worker` also refreshes parking within its exclusive sync lease even when pet data is still fresh. Use Redis locking for multiple hosts, or file locking only on one shared filesystem. No recurring sync loop was added to web processes, and Google data remains manual.

The acceptance target remains complete-answer P50 <= 5 seconds with no five-second prompt rule or short artificial response cutoff. Local real-model measurements on 30 October 2026 (eight synthetic requests, two rounds, concurrency two) returned eight completed answers: P50 3.479 seconds; nearest-rank P95/max 34.882 seconds. Plan-button requests took 2.325/2.545 seconds; simple restaurant-and-mall plans took 3.445/3.157 seconds; random plans took 3.513/34.882 seconds; contextual follow-ups took 4.584/15.826 seconds. The slow sample is retained. These are local HTTP-independent measurements, not a production SLA; network and provider tails still require observation.

## Local development with another checkout running

Defaults remain frontend `5174` and backend `8001`. To run this checkout independently:

```sh
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8002
PET_API_PROXY_TARGET=http://127.0.0.1:8002 npm --prefix frontend run dev -- --port 5175
```

Google data collection remains manual. The dedicated public-data synchronization worker is separate from the web process.
