"""Bounded PostgreSQL persistence. Credentials and conversation bodies never enter logs."""
import asyncio
import json
import logging

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
    def __init__(self, url='', *, pool_size=3):
        self.url, self.pool_size = url, pool_size
        self.pool = None
        self._lock = asyncio.Lock()

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
        try:
            async with asyncio.timeout(6):
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
        except Exception as exc:
            trace.storage_status = 'unavailable'
            logger.error('conversation_store_write_failed trace_id=%s error_type=%s', trace.trace_id, type(exc).__name__)

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

    async def aclose(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
