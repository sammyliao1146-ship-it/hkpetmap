import asyncio
import json
from types import SimpleNamespace as NS

from agents import Agent, Runner, RunConfig, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText, ResponseFunctionToolCall
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.observability.trace import TurnTrace, TraceHooks, current_trace, observed_response
from backend.app.config.container import Container
from backend.app.config.settings import Settings
from backend.app.models.assistant import ChatResponse
from main import app
from test_pet_data import service


class ToolModel(Model):
    def __init__(self):
        self.calls = 0

    async def get_response(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            output = [ResponseFunctionToolCall(type='function_call',call_id='real-call-1',name='lookup',arguments='{}')]
        else:
            output = [ResponseOutputMessage(id='msg1',type='message',role='assistant',status='completed',
                       content=[ResponseOutputText(type='output_text',text='Found',annotations=[])])]
        return ModelResponse(output=output,usage=Usage(requests=1,input_tokens=10,output_tokens=3,total_tokens=13),response_id=str(self.calls))

    async def stream_response(self,*args,**kwargs):
        from openai.types.responses import Response, ResponseCompletedEvent, ResponseUsage
        result=await self.get_response()
        response=Response.model_construct(id=result.response_id,output=result.output,
            usage=ResponseUsage(input_tokens=10,output_tokens=3,total_tokens=13,
                input_tokens_details={'cached_tokens':0,'cache_write_tokens':0},output_tokens_details={'reasoning_tokens':0}))
        yield ResponseCompletedEvent(type='response.completed',sequence_number=1,response=response)


def test_actual_sdk_hooks_count_each_model_and_tool_once():
    async def run():
        trace = TurnTrace('test_session','Find a restaurant','en')
        token = current_trace.set(trace)
        @function_tool
        async def lookup() -> str:
            return 'Saved restaurant'
        try:
            result = await Runner.run(Agent(name='Test',model=ToolModel(),tools=[lookup]),'Find one',
                                      hooks=TraceHooks('main_agent','test'),run_config=RunConfig(tracing_disabled=True))
            assert result.final_output == 'Found'
            assert trace.metrics()['model_calls'] == 2
            assert trace.metrics()['tool_calls'] == 1
            assert trace.metrics()['total_tokens'] == 26
            assert trace.metrics()['usage_complete'] is True
        finally:
            current_trace.reset(token)
    asyncio.run(run())


def test_context_isolation_partial_usage_and_failed_model_attempts():
    async def run_one(question, usage):
        trace = TurnTrace('shared_session',question,'en')
        token = current_trace.set(trace)
        async def call():
            await asyncio.sleep(.001)
            return NS(usage=usage)
        try:
            await observed_response('intent_classifier','test',call)
            if usage:
                async def missing():return NS(usage=None)
                await observed_response('answer_review','test',missing)
            return trace
        finally:
            current_trace.reset(token)
    async def run():
        a,b = await asyncio.gather(run_one('A',NS(input_tokens=12,output_tokens=3,total_tokens=15)),run_one('B',None))
        assert a.trace_id != b.trace_id
        assert a.metrics()['model_calls'] == 2 and a.metrics()['total_tokens'] == 15
        assert not a.metrics()['usage_complete']
        assert b.metrics()['total_tokens'] is None and b.metrics()['model_calls'] == 1
        assert current_trace.get() is None
        trace=TurnTrace('session_1','Fail','en');token=current_trace.set(trace)
        try:
            async def fail():raise TimeoutError('secret provider text')
            try:await observed_response('main_agent','test',fail)
            except TimeoutError:pass
            assert trace.spans[0]['status']=='error'
            assert trace.spans[0]['error_type']=='TimeoutError'
            assert 'secret' not in json.dumps(trace.spans)
        finally:current_trace.reset(token)
    asyncio.run(run())


class CaptureStore:
    def __init__(self):self.rows=[]
    async def save(self,trace):
        trace.storage_status='saved'
        self.rows.append(json.loads(json.dumps(trace.record(),default=str)))
    async def aclose(self):pass
    async def get(self,trace_id):return next((r for r in reversed(self.rows) if r['trace_id']==trace_id),None)
    async def session(self,session_id,limit,before):return [r for r in self.rows if r['session_id']==session_id and r['status']!='running'][-limit:]


def test_http_and_sse_success_error_and_private_trace_lookup(tmp_path,monkeypatch):
    svc,cache,client=service(tmp_path)
    container=Container(Settings(api_key='test',model='test',base_url='https://example.invalid',cors_origins=[],trace_admin_token='private-test-token'),cache,client,svc)
    store=CaptureStore();container.conversations=store
    app.state.container=container
    async def handle(payload,request,container,on_delta=None):
        trace=current_trace.get()
        async def call():return NS(usage=NS(input_tokens=5,output_tokens=2,total_tokens=7))
        await observed_response('intent_classifier','test',call)
        if payload.message=='error':raise HTTPException(503,'Unavailable')
        if on_delta:await on_delta('Answer')
        return ChatResponse(answer='Answer',model='test')
    monkeypatch.setattr('backend.app.routers.assistant._handle',handle)
    try:
        with TestClient(app) as api:
            response=api.post('/api/v1/assistant/chat',json={'message':'question','session_id':'test_session'})
            assert response.status_code==200
            body=response.json();trace_id=body['trace_id']
            assert response.headers['x-trace-id']==trace_id
            assert body['metrics']['total_tokens']==7 and body['metrics']['storage_status']=='saved'
            assert api.get('/api/v1/assistant/traces/'+trace_id).status_code==401
            auth={'Authorization':'Bearer private-test-token'}
            stored=api.get('/api/v1/assistant/traces/'+trace_id,headers=auth)
            assert stored.headers['cache-control']=='no-store'
            assert stored.json()['question']=='question' and stored.json()['answer']=='Answer'
            sse=api.post('/api/v1/assistant/chat/stream',json={'message':'stream','session_id':'test_session'})
            events=[json.loads(line[6:]) for line in sse.text.splitlines() if line.startswith('data: ')]
            assert [e['type'] for e in events]==['meta','delta','final']
            assert len({e['trace_id'] for e in events if 'trace_id' in e})==1
            assert events[-1]['metrics']['first_token_ms'] is not None
            for endpoint in ['/assistant/chat','/assistant/chat/stream']:
                r=api.post('/api/v1'+endpoint,json={'message':'error','session_id':'test_session'})
                e=r.json() if endpoint.endswith('/chat') else json.loads(r.text.split('data: ')[-1])
                assert e['trace_id'] and e['metrics']['model_calls']==1
                assert store.rows[-1]['status']=='error'
            assert api.get('/api/v1/assistant/conversations/test_session',headers=auth).json()['turns']
    finally:
        del app.state.container


def test_cancelled_turn_is_saved_and_context_reset():
    from backend.app.routers.assistant import _traced_turn
    from unittest.mock import patch
    async def run():
        store=CaptureStore();trace=TurnTrace('session_1','cancel','en')
        async def cancelled(*args):raise asyncio.CancelledError
        with patch('backend.app.routers.assistant._handle',cancelled):
            try:await _traced_turn(NS(),NS(),NS(conversations=store),trace)
            except asyncio.CancelledError:pass
        assert store.rows[-1]['status']=='cancelled'
        assert current_trace.get() is None
    asyncio.run(run())


def test_actual_sdk_streaming_hooks_include_every_model_turn():
    async def run():
        trace=TurnTrace('session_1','Find one','en');token=current_trace.set(trace)
        @function_tool
        async def lookup() -> str:return 'Found restaurant'
        try:
            result=Runner.run_streamed(Agent(name='Test',model=ToolModel(),tools=[lookup]),'Find one',
                hooks=TraceHooks('main_agent','test'),run_config=RunConfig(tracing_disabled=True))
            async for event in result.stream_events():pass
            assert result.final_output=='Found'
            assert trace.metrics()['total_tokens']==26
            assert trace.metrics()['model_calls']==2 and trace.metrics()['tool_calls']==1
        finally:current_trace.reset(token)
    asyncio.run(run())
