# Conversation traces and Render Postgres

Every accepted chat request has a server-generated `trace_<uuid>` ID. Both JSON and SSE responses expose `X-Trace-ID`. SSE sends a `meta` event immediately, followed by deltas and exactly one `final` or `error` when the request completes. A disconnect is recorded as `cancelled` when the process can finish cleanup; a process crash can leave the initial row `running`.

## Render setup

1. Create Render Postgres in the same region as the backend service.
2. Set **backend service** environment variable `DATABASE_URL` to the database's **Internal Database URL**. Do not use a `VITE_` variable or put database credentials in the frontend.
3. Optionally set `TRACE_ADMIN_TOKEN` to a strong random secret to enable private history retrieval. This is a server-only bearer credential. Without it the lookup endpoints return 404.
4. Deploy the backend with its updated Python dependencies (`pip install .` includes asyncpg). The database role needs permission to create tables and indexes. The first persisted chat creates `pet_chat_turns` and its indexes automatically, using a transaction and advisory lock to coordinate processes.
5. Send a new chat. Expand **Trace details** under the reply and confirm **Saved to database**. No URL configured displays **Database not configured**. A failed write displays **Database write failed** and emits `conversation_store_write_failed` with the trace ID and exception type, without logging database credentials or message text.

No database was provisioned by this code change. Existing conversations that expired from cache cannot be recovered. The short-term Redis memory is unchanged; durable history is a separate Postgres record, not automatically injected wholesale into model context.

## Stored records

`pet_chat_turns` contains one row per accepted turn:

- `trace_id` primary key, `session_id`, UTC `started_at`, language.
- Current user `question`, final `answer`, selected model and validated intent routing.
- `status`: running, success, refused, blocked, error, cancelled.
- JSONB `metrics` and `spans`: model/tool names, durations, reported usage and error types.

The question is saved before model execution and the same row is updated at completion. Failed/cancelled runs are kept. An outage does not invent a successful save or fail the entire assistant; there is no durable local-file fallback or promise of replay after an unsuccessful DB write. Use storage-status errors to monitor missed writes.

The schema has no automatic record deletion policy. Configure retention/backups for your deployment. Render's free Postgres is time limited; check the current service plan before relying on it for long-term records.

## Metrics semantics

- `model_calls`: observed classifier/reviewer requests plus SDK model steps, including failed steps. Transport-level retries are not individually instrumented; the pooled client currently has retries disabled.
- `tool_calls`: local function/MCP calls observed by SDK hooks plus hosted web search calls reported in the model output. Calls are counted separately from model steps.
- Token counts aggregate the classifier, main Agent, nested web-research Agent and reviewer. Counts are taken from provider usage; no text-length estimates. If only some calls report usage, totals are known subtotals and `usage_complete=false`. If no usage is available, values are null rather than a fabricated zero. A cache-only answer with no model calls has zero tokens.
- Cached input and reasoning tokens are subsets, not additional tokens to add to the total.
- `duration_ms` is server elapsed time through answer/error completion, including initial persistence but excluding the final DB write and browser/network time.
- `first_token_ms` is time to the first emitted nonempty text delta. It is null for nonstreaming/empty output.
- Hosted web-tool durations are null because the provider does not provide separate execution timing.
- `storage_status`: saved, disabled, unavailable. The UI displays it under Trace details. A saved response means the final DB write completed.

These are application-owned traces in your Postgres database. External OpenAI trace export remains disabled; no separate OpenAI dashboard login is needed.

## Private lookup

Both endpoints require `Authorization: Bearer <TRACE_ADMIN_TOKEN>` and return `Cache-Control: no-store`. End users receive their own request's metrics but there is no public transcript lookup.

```sh
curl -H "Authorization: Bearer $TRACE_ADMIN_TOKEN" \
  'https://hkpetmap.com/api/v1/assistant/traces/trace_REPLACE_ME'

curl -H "Authorization: Bearer $TRACE_ADMIN_TOKEN" \
  'https://hkpetmap.com/api/v1/assistant/conversations/SESSION_ID?limit=50'
```

Conversation results are newest first. For older turns, pass the response's ISO timestamp `next_before` as the URL-encoded `before` parameter. Limits are 1–100. Keep this token out of browser bundles and public URLs.

In Render's Postgres SQL console:

```sql
SELECT trace_id, session_id, started_at, status,
       metrics->>'total_tokens' AS total_tokens,
       metrics->>'duration_ms' AS duration_ms,
       question, answer
FROM pet_chat_turns
ORDER BY started_at DESC
LIMIT 50;
```

## Verification

```sh
.venv/bin/python -m pytest -q
# Optional real PostgreSQL integration: use a disposable database.
PET_TEST_DATABASE_URL='postgresql://.../disposable_test_database' \
  .venv/bin/python -m pytest backend/tests/test_conversation_postgres.py -q
npm --prefix frontend run build
```

Tests cover real SDK function calls and streaming, context isolation between concurrent turns, partial/missing usage, failure/cancellation persistence, private trace endpoints and a real Postgres reconnect/upsert/session-isolation integration. Browser UI checks use controlled SSE fixtures to validate metadata rendering, failure traces, both languages and mobile layout.
