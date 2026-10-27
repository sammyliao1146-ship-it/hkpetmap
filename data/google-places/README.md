# Google restaurant details — manual collection

- `index.json`: restaurant-to-candidate-ID relationships, file locations, collection summary; `automatic_updates: false`.
- `places/<GOOGLE_PLACE_ID>.json`: one record per unique candidate ID. `details` contains available Google fields, including name, address, rating, rating count, website, phones, opening hours, price, types, reviews and reservation attributes. Missing Google values remain absent, not assumed false.
- `photos/<GOOGLE_PLACE_ID>.<extension>`: at most one 800px-wide image per candidate ID. Photo metadata and author attribution are kept in its place record. `photo.local_path` is relative to this directory. Local image files do not require another Google request to read.
- `booking_url`, `menu_url`: first matching link actually found on the supplied official website homepage. All discovered alternatives, anchor text and source pages are in `website_links`. These are candidate links, not verified booking availability or parsed menu contents. A null link means it was not found, even if the venue accepts reservations.
- `cuisine`: Google place categories; not a complete or independently verified cuisine taxonomy.
- `errors`: failures are retained by stage; an absent website or photo does not erase successfully fetched details. `status: ready` means the details query succeeded, not that all optional fields exist.

## Matching

Records are keyed by Google Place ID, not by a potentially ambiguous restaurant name. `restaurant_ids` links back to the existing restaurant licence IDs. `index.json.restaurants` preserves `single_candidate`, `needs_review`, and `no_result` from the original ID search. Even single candidates are not independently verified. Do not automatically present a camp, shopping mall, or adjacent branch as the restaurant. This collection does not change the existing source snapshot, application API, or frontend.

## Updates

There is no scheduler, startup hook, or expiry-triggered request. Timestamps describe the collection time, not live freshness. Photo URLs can expire; the downloaded local file is recorded separately.

Run manually from the project root:

```bash
.venv/bin/python scripts/fetch_google_place_details.py
```

Existing records are reused without any refresh. To retry failed details queries explicitly:

```bash
.venv/bin/python scripts/fetch_google_place_details.py --retry-errors
```

Optional photo/website failures in otherwise-ready records are retained and are not automatically retried. All API credentials stay in the project `.env` or process environment; they are not included in exported data. Keep Google and contributor attribution when displaying content. Local collection does not grant additional storage or reuse rights.
