# Google facility photo availability audit

This is a manually triggered, resumable audit of non-restaurant facilities that have no photos after applying the existing official photo manifest. Existing official photographs are not changed.

- `index.json`: results keyed by the original facility ID, with name/address/category, queried text, candidate IDs, returned Google names/addresses, name similarity, distance, and status.
- `places/<GOOGLE_PLACE_ID>.json`: Google details for each unique candidate. `photo_count` is the count returned by the API (up to its response limit), not a count of all photographs on Google Maps. `photos` retains only the first photo resource and its attribution.
- `matched_with_photos`: the selected candidate passed name/distance checks and returned photos.
- `needs_review_with_photos`: some candidate returned photos, but identity remains ambiguous or below the matching threshold.
- `matched_without_photos`, `needs_review_without_photos`, `no_result`, `error`: missing photo data, search result, or request failure is explicitly preserved.

No image bytes or photo media URLs were requested. The audit does not replace frontend photographs or change facility names/coordinates. All API keys remain in `.env`; no keys are written to these files. Photo resources can expire and would need to be fetched again if used later. No automatic update, timer, or startup hook is installed.

Manual execution from project root:

```sh
.venv/bin/python -m scripts.check_google_facility_photos
```

Successful saved facility records are reused. Records with `error` are retried on a manual rerun.
