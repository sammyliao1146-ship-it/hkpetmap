"""Bounded PostgreSQL persistence. Credentials and conversation bodies never enter logs."""
import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS pet_chat_turns (
    trace_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    language TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    status TEXT NOT NULL,
    model TEXT,
    error_type TEXT,
    metrics JSONB NOT NULL DEFAULT '{}',
    routing JSONB,
    spans JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS pet_chat_session_time ON pet_chat_turns(session_id, started_at DESC, trace_id);
CREATE INDEX IF NOT EXISTS pet_chat_started_at ON pet_chat_turns(started_at DESC);
'''


class ConversationStore:
    def __init__(self, url='', *, pool_size=3, write_timeout=1.5):
        self.url, self.pool_size = url, pool_size
        self.pool = None
        self._lock = asyncio.Lock()
        self.write_timeout = write_timeout
        self._writes = asyncio.Semaphore(pool_size)

    async def initialize(self):
        if not self.url or self.pool:
            return
        async with self._lock:
            if self.pool:
                return
            import asyncpg
            pool = await asyncpg.create_pool(self.url, min_size=1, max_size=self.pool_size,
                                            timeout=5, command_timeout=5)
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute("SELECT pg_advisory_xact_lock(803192711)")
                        await conn.execute(SCHEMA)
            except BaseException:
                await pool.close()
                raise
            self.pool = pool

    async def save(self, trace):
        if not self.url:
            trace.storage_status = 'disabled'
            return
        started = time.perf_counter()
        for attempt in range(2):
            try:
                async with asyncio.timeout(self.write_timeout):
                    async with self._writes:
                        await self.initialize()
                        trace.storage_status = 'saved'
                        r = trace.record()
                        await self.pool.execute('''INSERT INTO pet_chat_turns
                    (trace_id,session_id,started_at,language,question,answer,status,model,error_type,metrics,routing,spans)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb)
                    ON CONFLICT (trace_id) DO UPDATE SET answer=EXCLUDED.answer,status=EXCLUDED.status,
                    model=EXCLUDED.model,error_type=EXCLUDED.error_type,metrics=EXCLUDED.metrics,
                    routing=EXCLUDED.routing,spans=EXCLUDED.spans''',
                    r['trace_id'],r['session_id'],r['started_at'],r['language'],r['question'],r['answer'],
                    r['status'],r['model'],r['error_type'],json.dumps(r['metrics']),
                    json.dumps(r['routing']),json.dumps(r['spans']))
                logger.info('conversation_store_write trace_id=%s duration_ms=%.1f attempts=%s',
                            trace.trace_id, (time.perf_counter()-started)*1000, attempt+1)
                return
            except Exception as exc:
                trace.storage_status = 'unavailable'
                if attempt == 0:
                    await asyncio.sleep(.1)
                else:
                    logger.error('conversation_store_write_failed trace_id=%s error_type=%s duration_ms=%.1f',
                                 trace.trace_id, type(exc).__name__, (time.perf_counter()-started)*1000)

    @staticmethod
    def decode(row):
        if row is None:
            return None
        value = dict(row)
        for key in ('metrics','routing','spans'):
            if isinstance(value[key], str):
                value[key] = json.loads(value[key])
        return value

    async def get(self, trace_id):
        await self.initialize()
        if not self.pool:
            return None
        return self.decode(await self.pool.fetchrow('SELECT * FROM pet_chat_turns WHERE trace_id=$1', trace_id))

    async def session(self, session_id, limit=50, before=None):
        await self.initialize()
        if not self.pool:
            return []
        rows = await self.pool.fetch('''SELECT * FROM pet_chat_turns WHERE session_id=$1
            AND ($3::timestamptz IS NULL OR started_at<$3) ORDER BY started_at DESC,trace_id DESC LIMIT $2''', session_id,limit,before)
        return [self.decode(row) for row in rows]

    async def stats(self, days=7):
        await self.initialize()
        if not self.pool:
            raise RuntimeError('Storage disabled')
        row = await self.pool.fetchrow('''SELECT count(*) AS turns,
            count(*) FILTER (WHERE status='success') AS completed_answers,
            count(*) FILTER (WHERE status IN ('error','timeout')) AS errors,
            count(*) FILTER (WHERE status='running') AS running,
            sum((metrics->>'total_tokens')::bigint) AS reported_tokens,
            count(*) FILTER (WHERE (metrics->>'usage_complete')::boolean IS TRUE) AS complete_usage_turns,
            percentile_cont(.5) WITHIN GROUP (ORDER BY (metrics->>'duration_ms')::double precision)
                FILTER (WHERE status<>'running') AS duration_p50_ms,
            percentile_cont(.95) WITHIN GROUP (ORDER BY (metrics->>'duration_ms')::double precision)
                FILTER (WHERE status<>'running') AS duration_p95_ms,
            percentile_cont(.5) WITHIN GROUP (ORDER BY (metrics->>'duration_ms')::double precision)
                FILTER (WHERE status='success') AS answer_duration_p50_ms,
            percentile_cont(.95) WITHIN GROUP (ORDER BY (metrics->>'duration_ms')::double precision)
                FILTER (WHERE status='success') AS answer_duration_p95_ms,
            percentile_cont(.5) WITHIN GROUP (ORDER BY (metrics->>'first_token_ms')::double precision) AS first_text_p50_ms,
            percentile_cont(.95) WITHIN GROUP (ORDER BY (metrics->>'first_token_ms')::double precision) AS first_text_p95_ms,
            avg((metrics->>'model_calls')::double precision) AS mean_model_calls
            FROM pet_chat_turns WHERE started_at >= now()-make_interval(days => $1)''', days)
        return {'days':days, **dict(row)}

    async def recent(self, limit=50, before=None):
        await self.initialize()
        if not self.pool:
            raise RuntimeError('Storage disabled')
        rows = await self.pool.fetch('''SELECT trace_id,session_id,started_at,question,status,model,metrics
            FROM pet_chat_turns WHERE ($2::timestamptz IS NULL OR started_at<$2)
            ORDER BY started_at DESC,trace_id DESC LIMIT $1''', limit, before)
        values = []
        for row in rows:
            value = dict(row)
            if isinstance(value['metrics'], str):
                value['metrics'] = json.loads(value['metrics'])
            values.append(value)
        return values

    async def prune(self, days=0, *, apply=False, batch_size=1000, max_batches=100):
        # Opt-in maintenance only. There is no automatic deletion on application startup.
        if days <= 0:
            return {'enabled':False, 'deleted':0}
        await self.initialize()
        if not self.pool:
            raise RuntimeError('Storage disabled')
        count = await self.pool.fetchval('SELECT count(*) FROM pet_chat_turns WHERE started_at<now()-make_interval(days => $1)', days)
        deleted = 0
        if apply:
            for _ in range(max_batches):
                status = await self.pool.execute('''DELETE FROM pet_chat_turns WHERE trace_id IN (
                    SELECT trace_id FROM pet_chat_turns WHERE started_at<now()-make_interval(days => $1)
                    ORDER BY started_at LIMIT $2)''', days, batch_size)
                n = int(status.rsplit(' ', 1)[-1]); deleted += n
                if n < batch_size:
                    break
        return {'enabled':True, 'dry_run':not apply, 'eligible':count, 'deleted':deleted}

    async def aclose(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
