"""Real Postgres integration; PET_TEST_DATABASE_URL must point to a disposable database."""
import asyncio
import os
from types import SimpleNamespace as NS

import pytest
from backend.app.observability.store import ConversationStore
from backend.app.observability.trace import TurnTrace


@pytest.mark.skipif(not os.getenv('PET_TEST_DATABASE_URL'),reason='Disposable Postgres URL not supplied')
def test_postgres_upsert_restart_and_session_boundaries():
    async def run():
        url=os.environ['PET_TEST_DATABASE_URL']
        from uuid import uuid4
        suffix=uuid4().hex
        session_a='session_a_'+suffix;session_b='session_b_'+suffix
        store=ConversationStore(url)
        a=TurnTrace(session_a,'Where is the restaurant?','en')
        b=TurnTrace(session_b,'Different user','en')
        await asyncio.gather(store.save(a),store.save(b))
        assert a.storage_status==b.storage_status=='saved'
        span=a.start('model','classifier','test')
        a.end(span,usage=NS(input_tokens=10,output_tokens=4,total_tokens=14))
        a.finish('success',NS(answer='Answer',model='test',routing=None))
        await store.save(a)
        assert len(await store.session(session_a))==1  # upsert, not a duplicate message
        await store.aclose()
        # A fresh process/pool can recover the completed transcript and measurements.
        reopened=ConversationStore(url)
        row=await reopened.get(a.trace_id)
        assert row['question']==a.question and row['answer']=='Answer'
        assert row['status']=='success' and row['metrics']['total_tokens']==14
        assert row['spans'][0]['name']=='classifier'
        assert (await reopened.session(session_b))[0]['question']=='Different user'
        assert await reopened.session(session_a,before=row['started_at'])==[]
        assert await reopened.get('nonexistent') is None
        stats=await reopened.stats(7)
        assert stats['turns']>=2 and stats['reported_tokens']>=14
        assert stats['duration_p50_ms'] is not None
        assert stats['completed_answers']>=1 and stats['answer_duration_p50_ms'] is not None
        assert any(r['trace_id']==a.trace_id for r in await reopened.recent())
        # Old rows are counted in dry-run but removed only by explicit apply.
        old=TurnTrace('retention_test','old record','en')
        from datetime import timedelta
        old.started_at -= timedelta(days=100)
        await reopened.save(old)
        report=await reopened.prune(90)
        assert report['dry_run'] and report['eligible']>=1 and report['deleted']==0
        assert await reopened.get(old.trace_id)
        applied=await reopened.prune(90,apply=True,batch_size=1)
        assert applied['deleted']>=1 and await reopened.get(old.trace_id) is None
        await reopened.aclose()
    asyncio.run(run())


def test_database_failure_is_explicit_and_disabled_is_not_saved():
    async def run():
        trace=TurnTrace('session_a','question','en')
        disabled=ConversationStore()
        await disabled.save(trace)
        assert trace.storage_status=='disabled'
        class BrokenPool:
            async def execute(self,*args):raise OSError('fake database failure')
        store=ConversationStore('postgresql://not-used')
        store.pool=BrokenPool()
        await store.save(trace)
        assert trace.storage_status=='unavailable'
    asyncio.run(run())
