# Saved restaurant and facility query caching

All published restaurants and facilities now share an Agent query index and a
versioned result cache. This is separate from Cloudflare response caching and
from the curated 150-restaurant featured shortlist.

## Data and index

`AgentPlaceIndex` holds every saved venue, with category, cuisine and district
indexes and each venue's exact saved coordinates. Multiple cuisine labels do
not duplicate venues. Indexing does not discard unrated facilities or restrict
the dataset to a high-rating shortlist. Rating/price/radius filters and ordering
run over the complete eligible set before applying the requested limit.

Snapshot loading builds the index once after manual Google enrichment and local
photo metadata have been attached. Snapshot replacement invalidates it; query
code can also lazily build it for an injected or newly published snapshot.
Reviews, photos and photo-attribution payloads are excluded from the query index
and result cache. Details and existing media endpoints retain their own behavior.
Saved policies, source URLs, rating counts, price ranges and unknown values are
preserved, including the distinction between third-party mall directories and
official checks.

## Result reuse

`PetDataAccess.search_places` and supported fast cuisine/price answers use
`PetService.search_agent_places`:

1. Normalize existing mode/cuisine aliases and Chinese/English district aliases.
2. Hash the dataset revision and complete filter parameters into
   `place-query:v1:<sha256>`, under the existing Redis namespace.
3. Read the process-local L1, then shared Redis L2; compute on a miss.
4. Return a separate mutable result to each caller and register its source/place
   references in that caller's Agent context, including on cache hits.

Keys include category, cuisine, district, literal name/address query, sort order,
limit, minimum rating, maximum price, radius, exact origin and the policy for
excluding review candidates. They do not include conversation IDs or user text
outside these explicit search filters. Results contain both saved languages,
so equivalent Chinese/English filters share records while answer rendering uses
the user's requested language. Nearby queries do not round the user's location.
Random draws reuse the complete index but bypass result caching.

L1 is bounded to 512 entries / 8 MiB with expiry and LRU eviction. Results expire
after 600 seconds in L1/L2. A new dataset revision or freshness status immediately
uses new keys; obsolete entries expire or are evicted. Manual data publication
therefore invalidates results without triggering Google refreshes. Cache reads
and writes each have a 100 ms wait limit; an unavailable cache falls back to
computing from saved data. Concurrent identical misses share one fill in a
process, and one disconnected waiter does not cancel another user's fill.

The index/revision/metadata used for a miss are captured before awaiting Redis.
A snapshot published during the read cannot be saved under the preceding
version's key. Shutdown cancels outstanding fills and releases the L1.

## Boundaries and verification

This caches structured place queries, not arbitrary final model answers or
personalized conversation histories. Plans that use the place tools reuse these
candidate queries; a complete itinerary, live parking vacancy or newly researched
opening hours is not treated as a ten-minute static place query. Model intent
classification, generation and review still have their own latency. No short
generation deadline or five-second prompt rule was added.

The read-only `/api/v1/assistant/capabilities` endpoint reports
`saved_place_queries.cache_version = "place-query:v1"` after this backend is
deployed, allowing rollout verification without exposing conversation traces.

`backend/tests/test_place_query_cache.py` covers cross-user and cross-service
hits, alias normalization, the complete ranking set, unrated facilities, source
registration, coordinate/filter isolation, snapshot/status invalidation,
snapshot publication during a miss, cache failures, concurrent cancellation,
capacity/expiry and random draws. Existing delivery tests still verify per-turn
read coalescing and media/review exclusion.
