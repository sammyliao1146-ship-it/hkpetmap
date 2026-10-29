# Delivery and Agent performance

The application keeps Google enrichment manual and conversation traces private. This change does not fetch new Google information or introduce shared caching of Google photos/reviews/ratings.

## Follow-up optimisations

- Nearby recommendations check the content revision and cache before serialising restaurant records. Concurrent misses share work per location/language/revision; different locations share a single featured-index rebuild per revision. A cancelled waiter does not cancel another user's read. Work remains bounded and is cancelled on shutdown.
- Initial Postgres writes overlap Agent work and are joined before the final upsert. Pool warmup, two bounded write attempts and write-latency logging reduce startup/database stalls without an untracked background queue. Failed writes remain explicit; no durable replay is claimed.
- Validated intent selects the function/MCP tool allowlist. Map searches use place/activity tools, transport uses place/directions/transport tools, and policy/planning may use restricted web research. Exact, unique saved phone/website requests can return a sourced template after the intent gate; ambiguous, compound and freshness-sensitive requests continue through the existing Agent/guardrails.
- `python -m scripts.build_photo_variants` precomputes existing local originals into content-keyed `.variants` WebP files. HTTP serves these directly across process restarts. Startup gradually prepares missing variants in a background worker; `PHOTO_PREGENERATE=false` disables it. The CLI can also run after manual imports or during the deployment build. No network or Google refresh is involved. Originals/attribution and private cache policy remain intact; read-only disks fall back to on-demand resizing. A fresh ephemeral deployment still needs pre-generation unless variants are included in its build artifact. Old content-keyed variants are not automatically deleted.
- The map groups nearby points into count markers below zoom 15, zooms in on cluster click, and mounts markers only in the padded viewport. A selected offscreen place and colocated venues are retained so card selection still opens the popup. Plan results retain individual markers. Counts reflect the current filter and padded viewport, not all Hong Kong places.
- The private conversation monitor and opt-in retention command are documented in `CONVERSATION_TRACING.md`.

## Photos

Local photo handlers accept `size=thumb` (maximum edge 240 px), `size=detail` (768 px, default), and `size=original`. They generate WebP at quality 76 in a worker thread and preserve attribution and original files. Resize concurrency is bounded to two; the per-process derivative cache is bounded to 64 entries / 8 MiB. Oversized/unreadable images fall back to the validated original. Browser caching retains the existing `private, max-age=86400` policy; source file metadata changes invalidate ETags. The frontend also includes the dataset version in local photo URLs. External source images retain their original URLs and policies; they are not proxied.

## Agent

- The compact catalogue/time is supplied once in `map_context`. The default function-tool Agent no longer offers a redundant catalogue-first call.
- Search defaults to five results. Ranking/filtering still covers all matching records before limiting results.
- Search results omit reviews, image metadata and irrelevant global sources. Details include contact information, policies, hours, price and source links; explicit review requests return at most two 500-character excerpts.
- Identical read calls within one turn share work; no conversation results are shared between users. Random sampling bypasses memoisation. A published snapshot replacement changes the memo key.
- Recent known place IDs are derived from the latest assistant message and reintroduced as untrusted entity context, avoiding rediscovery when the reference is unambiguous. User constraints remain intact; prior assistant text is bounded to 2,400 characters per message and the latest six messages.
- All safety boundaries, local-versus-live provenance and private Postgres tracing remain in place.

## Version checks and lazy details

On first load the app reads `/data-version`, the catalogue and `/place-summaries`. Every five minutes a visible tab checks the small version response. An unchanged version does not download either collection again. Hidden tabs stop checking; a returning stale tab checks immediately. These checks read published data and never trigger Google refreshes.

Summaries retain name/address search fields, coordinates, cuisine/rating/price-card data, mall badges and the original pet-park amenity descriptions used by filters. Full reviews, hours and gallery metadata load only when a popup opens through `/places/{id}`. The browser retains at most 64 detail records per dataset revision. Errors allow retry. Popup size is recalculated after async content/images and map movement.

Existing `/places` consumers retain the full-record interface. A newly deployed frontend falls back on 404 to the old endpoints during rolling deploys. Version identifiers are based on enriched content and freshness state, not per-replica checkout timestamps. Manual local manifest/profile changes trigger snapshot reload without upstream requests.

## Cache policy

Worker request screening runs before API proxying or static asset handling. Sensitive dotfile/credential probes return a non-cacheable 404, including encoded path variants. The backend repeats this check before routing for direct Render traffic. Screening inspects paths only, so search/chat query text is unaffected. Workers must run first on all paths for this protection to cover root-level probes; `wrangler.jsonc` enables that setting.

| Resource | Policy |
| --- | --- |
| Hashed `/assets/*` | Browser cache one year, immutable; Cloudflare Static Assets serves the files |
| HTML | Default validation; index.html explicitly no-cache |
| Catalogue | Public Worker cache 300 s; version query keys separate publications |
| Data-version | Public Worker cache 30 s |
| Activities | Public Worker cache 60 s; UI still issues one request per refresh click |
| Non-location parking collection | Public Worker cache 30 s; vacancies retain upstream timestamps/staleness flags |
| Summary/detail/legacy place responses containing Google data | No shared Worker cache; summary supports private browser ETag validation, detail/legacy no-store |
| Google-derived local photos | Private browser cache only; no extension of shared-cache permissions |
| Chat, Plan, histories, authenticated/cookie/location requests, errors | Bypass shared cache; private/no-store where appropriate |

The Worker uses an exact public GET allowlist, preserves query/language keys and respects private/no-store/Set-Cookie. Cache hits do not reuse another origin request ID. Only successful JSON responses are stored. The Cache API is per Cloudflare data centre and this implementation does not collapse a concurrent cold-miss burst.

ETags and pre-serialised summary/catalogue/version bytes avoid re-encoding unchanged collections in each backend process. Cache misses and Render cold starts still incur origin latency. Overall cache-hit percentage need not rise dramatically because private and Google-derived responses intentionally bypass shared caches.

## Local measurements on the saved 1,721-place dataset

| Measurement | Before | After |
| --- | ---: | ---: |
| Place collection JSON | 11,749,410 bytes | 2,355,741 bytes |
| Gzip collection | 2,684,867 bytes | 293,068 bytes (89% smaller) |
| Five highest-rated restaurant results, JSON | 40,084 bytes | 10,987 bytes (73% smaller) |
| Five local photo samples | 87–161 KB each | 5–9 KB thumbnails; 38–73 KB detail images |

These are payload measurements, not measured production latency, token bills or guaranteed global CDN-hit rates. Validate production p50/p95, first-content latency, origin request counts and 5xx separately after deployment.

## Checks

```sh
python -m pytest -q
node --test frontend/scripts/worker-cache.test.mjs
npm --prefix frontend run build
```

Coverage includes source-preserving resizing, bounded variants, ETags, publication invalidation, map/detail separation, exact ranking data, repeated-tool reuse, private trace regression and Worker bypass rules. Browser checks exercise the five-minute clock, hidden-tab pause, lazy fetch/reopen and original amenity filters.
