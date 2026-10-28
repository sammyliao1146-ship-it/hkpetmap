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
        store=ConversationStore(url)
        a=TurnTrace('session_a','Where is the restaurant?','en')
        b=TurnTrace('session_b','Different user','en')
        await asyncio.gather(store.save(a),store.save(b))
        assert a.storage_status==b.storage_status=='saved'
        span=a.start('model','classifier','test')
        a.end(span,usage=NS(input_tokens=10,output_tokens=4,total_tokens=14))
        a.finish('success',NS(answer='Answer',model='test',routing=None))
        await store.save(a)
        assert len(await store.session('session_a'))==1  # upsert, not a duplicate message
        await store.aclose()
        # A fresh process/pool can recover the completed transcript and measurements.
        reopened=ConversationStore(url)
        row=await reopened.get(a.trace_id)
        assert row['question']==a.question and row['answer']=='Answer'
        assert row['status']=='success' and row['metrics']['total_tokens']==14
        assert row['spans'][0]['name']=='classifier'
        assert (await reopened.session('session_b'))[0]['question']=='Different user'
        assert await reopened.session('session_a',before=row['started_at'])==[]
        assert await reopened.get('nonexistent') is None
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
