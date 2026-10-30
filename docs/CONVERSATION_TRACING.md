# Conversation traces and Render Postgres

Every accepted chat request has an internal server-generated `trace_<uuid>` ID. Public JSON/SSE responses and headers do not expose trace IDs, usage, timing, call counts, spans or storage status. SSE sends text deltas and exactly one `final` or `error` when the request completes. A disconnect is recorded as `cancelled` when the process can finish cleanup; a process crash can leave the initial row `running`.

## Render setup

1. Create Render Postgres in the same region as the backend service.
2. Set **backend service** environment variable `DATABASE_URL` to the database's **Internal Database URL**. Do not use a `VITE_` variable or put database credentials in the frontend.
3. Optionally set `TRACE_ADMIN_TOKEN` to a strong random secret to enable private history retrieval. This is a server-only bearer credential. Without it the lookup endpoints return 404.
4. Deploy the backend with its updated Python dependencies (`pip install .` includes asyncpg). The database role needs permission to create tables and indexes. The first persisted chat creates `pet_chat_turns` and its indexes automatically, using a transaction and advisory lock to coordinate processes.
5. Send a new chat, then verify the newest row in `pet_chat_turns` through psql/a database client, or the authenticated conversation lookup endpoint using its session ID. The public chat UI intentionally contains no operational metrics. A failed write emits `conversation_store_write_failed` with the internal trace ID and exception type, without logging credentials or message text.

No database was provisioned by this code change. Existing conversations that expired from cache cannot be recovered. The short-term Redis memory is unchanged; durable history is a separate Postgres record, not automatically injected wholesale into model context.

## Stored records

`pet_chat_turns` contains one row per accepted turn:

- `trace_id` primary key, `session_id`, UTC `started_at`, language.
- Current user `question`, final `answer`, selected model and validated intent routing.
- `status`: running, success, refused, blocked, error, timeout, cancelled. A time-budget response is a timeout, not a successful verified answer.
- JSONB `metrics` and `spans`: model/tool names, durations, reported usage and error types.

The initial save runs alongside model execution and is joined before the final upsert. HTTP/SSE sends the completed answer before running the final persistence continuation through Starlette BackgroundTasks; graceful shutdown waits for it. Failed/cancelled runs are kept. This is not a durable queue: abrupt process/host loss can leave a running row or lose an unsaved turn. Startup warms the pool; writes are limited to the pool size and have two bounded attempts (1.5 seconds each, 100 ms retry delay). Storage errors remain explicit. Logs include write duration and attempts, without conversation text or credentials.

Automatic deletion is disabled. The optional `python -m scripts.prune_conversations --days 90` previews eligible rows; add `--apply` to delete in batches of at most 1,000 (at most 100 batches per invocation). `TRACE_RETENTION_DAYS=0` is the default if no argument is supplied. Nothing schedules or applies deletion automatically. Backups remain the deployment operator's responsibility.

## Metrics semantics

- `model_calls`: observed classifier/reviewer requests plus SDK model steps, including failed steps. Transport-level retries are not individually instrumented; the pooled client currently has retries disabled.
- `tool_calls`: local function/MCP calls observed by SDK hooks plus hosted web search calls reported in the model output. Calls are counted separately from model steps.
- Token counts aggregate the classifier, main Agent, nested web-research Agent and reviewer. Counts are taken from provider usage; no text-length estimates. If only some calls report usage, totals are known subtotals and `usage_complete=false`. If no usage is available, values are null rather than a fabricated zero. A cache-only answer with no model calls has zero tokens.
- Cached input and reasoning tokens are subsets, not additional tokens to add to the total.
- `duration_ms` is server elapsed time through answer/error completion. The initial DB write overlaps model work; the duration excludes any remaining persistence wait, the final upsert and browser/network time. Use database-write log durations to diagnose persistence latency.
- `first_token_ms` is time to the first emitted nonempty text delta. Only completed/approved answers are released; it is not the provider's first generated draft token. It is null for nonstreaming/empty output.
- Hosted web-tool durations are null because the provider does not provide separate execution timing.
- `storage_status`: saved, disabled, unavailable. This is an internal diagnostic field; it is not sent to public chat clients. A final saved row means the final DB write completed.

These are application-owned traces in your Postgres database. External OpenAI trace export remains disabled; no separate OpenAI dashboard login is needed.

## Private lookup

Open `https://hkpetmap.com/api/v1/assistant/admin` after deploying this version. This is a data-free shell; enter `TRACE_ADMIN_TOKEN` to load protected statistics and recent turns. The token stays in page memory, never localStorage, cookies or the URL; Clear and closing/leaving the page erase it. The shell has noindex/no-store, a nonce-based CSP and no external resources. Do not use a shared computer. Public chat responses still contain no trace metrics.

Authenticated endpoints `/assistant/admin/stats?days=7` (1–30 days), `/assistant/admin/turns` and `/assistant/admin/trace/{id}` provide reported token subtotals, usage completeness, response p50/p95, first-text p50/p95, mean model calls and paginated recent questions. Successful chat-answer p50/p95 (`answer_duration_p50_ms`, `answer_duration_p95_ms`) exclude refused, blocked, errored, running and timeout turns; all-turn duration percentiles remain available separately. Structured Plan timing is measured by the HTTP benchmark, not this conversation table. Null timings mean unavailable, not zero; cancelled/refused/blocked counts remain visible in individual turns. Statistics are computed in Postgres over the indexed time window.

Both endpoints require `Authorization: Bearer <TRACE_ADMIN_TOKEN>` and return `Cache-Control: no-store`. Metrics and transcripts are available only through these authenticated endpoints or a direct authorised database connection. There is no public transcript or diagnostic lookup.

```sh
curl -H "Authorization: Bearer $TRACE_ADMIN_TOKEN" \
  'https://hkpetmap.com/api/v1/assistant/traces/trace_REPLACE_ME'

curl -H "Authorization: Bearer $TRACE_ADMIN_TOKEN" \
  'https://hkpetmap.com/api/v1/assistant/conversations/SESSION_ID?limit=50'
```

Conversation results are newest first. For older turns, pass the response's ISO timestamp `next_before` as the URL-encoded `before` parameter. Limits are 1–100. Keep this token out of browser bundles and public URLs.

Using psql or a database client connected to Render Postgres:

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

Tests cover real SDK function calls and streaming, context isolation between concurrent turns, partial/missing usage, failure/cancellation persistence, private trace endpoints and a real Postgres reconnect/upsert/session-isolation integration. Privacy regression tests verify success and error JSON/SSE responses omit diagnostics while authenticated lookups and database records retain them. The public chat UI does not render Trace/Token/storage details, even if an older backend sends them during a rolling deployment.
