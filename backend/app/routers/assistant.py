import asyncio
import copy
import dataclasses
import json
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from pathlib import Path

from agent.data.data_access import PetDataAccess
from agent.assembly.service import run_pet_assistant
from agent.subagents.web_knowledge import WebKnowledgeService,DOMAINS
from agent.subagents.intent_router import classify_intent, route_action, gate_reply, assistant_intro_reply
from agent.subagents.answer_guard import review_answer, blocked_reply
from agent.data.tools.pet_data import make_pet_queries
from agent.memory.conversation import ConversationMemory
from agent.data.featured_answer import is_simple_nearby, render_nearby
from agent.data.saved_lookup import saved_lookup
from agent.data.fast_answers import fast_answer
from backend.app.config.container import Container
from backend.app.config.dependencies import get_container
from backend.app.observability.trace import TurnTrace, current_trace
from backend.app.models.assistant import ChatOrigin, ChatRequest, ChatResponse, IntentRouting, PrefillRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["assistant"])


def _access(container: Container, origin=None) -> PetDataAccess:
    return PetDataAccess(container.pets,origin=origin,parking=getattr(container,'parking',None))


@router.get("/assistant/capabilities")
async def capabilities(container: Container = Depends(get_container)) -> dict:
    from agents import function_tool

    tools = [function_tool(query) for query in make_pet_queries(_access(container))]+[WebKnowledgeService(container.settings).tool()]
    return {
        "read_only": True,
        "web_knowledge":{"model":container.settings.web_search_model,"domain_filtered":True,"topics":list(DOMAINS),"medical_diagnosis":False},
        "answer_guard":{"model":container.settings.intent_model,"checks":["relevance","scope","request_match"],"fail_closed":True},
        "intent_router": {"model":container.settings.intent_model,
                          "confidence_threshold":container.settings.intent_confidence_threshold,
                          "intents":["map_query","trip_plan","transport","pet_policy","pet_health","restaurant_info","assistant_identity"],
                          "low_confidence":"clarify","out_of_scope":"refuse"},
        "transports": ["function", "mcp_stdio"],
        "tools": [{"name": t.name, "description": t.description, "input_schema": t.params_json_schema} for t in tools],
        "unsupported": ["booking", "payment", "login", "route and travel-time estimates", "arbitrary web access"],
    }


NEARBY_TTL_SECONDS = 600
NEARBY_LIMIT = 5


async def _nearby_featured(container: Container, origin: ChatOrigin, language: str) -> dict:
    """Featured restaurants nearest to the origin, answered from cache (10 min TTL, ~100 m grid)."""
    version = container.pets.data_revision()
    key = f"nearby:v2:{version}:{language}:{origin.latitude:.3f}:{origin.longitude:.3f}"
    cached = await container.cache.get_json(key)
    if cached:
        return cached
    async def fill():
        # Another waiter may have filled the shared Redis cache in the meantime.
        cached = await container.cache.get_json(key)
        if cached:
            return cached
        async def prepare():
            if container.featured.version != version:
                data = container.pets.places(mode='restaurants', for_agent=True)
                await asyncio.to_thread(container.featured.ensure, data['items'], version)
        await container.nearby_flights.run(('featured', version), prepare)
        rows = await asyncio.to_thread(container.featured.nearest, origin.latitude, origin.longitude, NEARBY_LIMIT)
        selected={r['id'] for r in rows}
        sources={str(p.source_url):{'url':str(p.source_url),'title':p.source_name} for p in (container.pets.snapshot.places if container.pets.snapshot else []) if p.id in selected}
        value = {'answer': render_nearby(rows, language), 'places': [{'id': r['id'], 'name': r['name']} for r in rows], 'sources':list(sources.values())}
        await container.cache.set_json(key, value, NEARBY_TTL_SECONDS)
        return value
    return await container.nearby_flights.run(key, fill)


@router.post("/assistant/prefill")
async def prefill(payload: PrefillRequest, container: Container = Depends(get_container)) -> dict:
    """Warm the nearby-answer cache when the user shares a location."""
    value = await _nearby_featured(container, ChatOrigin(latitude=payload.latitude, longitude=payload.longitude), payload.language)
    return {"cached": True, "count": len(value['places'])}


async def _traced_turn(payload, request, container, trace, on_delta=None, background_tasks=None):
    token = current_trace.set(trace)
    # Start persistence alongside model work; always join it before the final upsert.
    # No detached/unreliable fire-and-forget queue is used.
    initial_save = asyncio.create_task(container.conversations.save(trace))
    try:
        budget=getattr(getattr(container,'settings',None),'chat_response_budget_seconds',4.0)
        try:
            async with asyncio.timeout(budget):
                # Release only the completed/approved answer. A timed-out or rejected
                # draft must not have already been streamed to the browser.
                response = await _handle(payload, request, container, None)
        except TimeoutError:
            response = budget_reply(payload.language)
        if on_delta and response.answer:
            trace.delta(response.answer)
            await on_delta(response.answer)
        trace.finish('timeout' if response.model=='time-budget' else 'blocked' if response.answer == blocked_reply(payload.language) else 'refused' if response.routing and response.routing.action == 'refuse' else 'success', response,
                     error=TimeoutError() if response.model=='time-budget' else None)
        return response
    except asyncio.CancelledError as exc:
        trace.finish('cancelled', error=exc)
        raise
    except BaseException as exc:
        trace.finish('error', error=exc)
        raise
    finally:
        # Cancellation must not discard the accepted turn or its final status.
        async def persist_turn():
            await asyncio.shield(initial_save)
            await asyncio.shield(container.conversations.save(trace))
            logger.info('agent_turn trace_id=%s status=%s model_calls=%s duration_ms=%s storage=%s',
                        trace.trace_id, trace.status, trace.metrics()['model_calls'], trace.duration_ms, trace.storage_status)
        try:
            if background_tasks is not None:
                # Starlette awaits this after sending the body and during graceful shutdown.
                # It is not a durable queue; an abrupt process loss can leave a running row.
                background_tasks.add_task(persist_turn)
            else:
                await persist_turn()
        finally:
            current_trace.reset(token)


def budget_reply(language):
    answer = ('I could not verify a complete answer within the response time limit. No new hours, rules or route have been confirmed. '
              'Please choose a specific place on the map for its saved details, or narrow your question.' if language=='en' else
              '未能喺回覆時限內完成核實，暫未確認新嘅營業時間、規定或路線。你可以喺地圖揀指定場地睇已儲存資料，或縮窄問題再查。')
    return ChatResponse(answer=answer,model='time-budget',degraded=True)


@router.post("/assistant/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, response: Response,
               background_tasks: BackgroundTasks,
               container: Container = Depends(get_container)):
    trace = TurnTrace(payload.session_id, payload.message, payload.language)
    try:
        result = await _traced_turn(payload, request, container, trace, background_tasks=background_tasks)
        return result
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, headers=exc.headers,
                            content={'detail':exc.detail})
    except Exception:
        logger.error('chat_failed trace_id=%s',trace.trace_id)
        return JSONResponse(status_code=500,
                            content={'detail':'The assistant is temporarily unavailable. Please try again.'})


@router.post("/assistant/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request, background_tasks:BackgroundTasks, container: Container = Depends(get_container)):
    trace = TurnTrace(payload.session_id, payload.message, payload.language)
    queue = asyncio.Queue(maxsize=64)

    async def on_delta(text):
        await queue.put({'type':'delta','text':text})

    async def work():
        try:
            response = await _traced_turn(payload, request, container, trace, on_delta, background_tasks)
            await queue.put({'type':'final',**response.model_dump()})
        except HTTPException as exc:
            await queue.put({'type':'error','status':exc.status_code,'detail':exc.detail})
        except Exception:
            logger.error('stream_failed trace_id=%s',trace.trace_id)
            await queue.put({'type':'error','status':500,'detail':'The assistant is temporarily unavailable. Please try again.'})
        finally:
            if not asyncio.current_task().cancelling():
                await queue.put(None)

    async def events():
        # Start only when the response body is consumed, avoiding orphan work on disconnect.
        task = asyncio.create_task(work())
        try:
            while (item := await queue.get()) is not None:
                yield f"data: {json.dumps(item,ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(events(),media_type='text/event-stream',
                             headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'},background=background_tasks)


def _trace_admin(request: Request, authorization: str | None = Header(default=None)):
    expected = request.app.state.container.settings.trace_admin_token
    if not expected:
        raise HTTPException(404,'Not found')
    supplied = authorization.removeprefix('Bearer ') if authorization and authorization.startswith('Bearer ') else ''
    if not secrets.compare_digest(supplied.encode(),expected.encode()):
        raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Bearer'})


@router.get('/assistant/admin', response_class=HTMLResponse)
async def admin_shell():
    # Public shell only. Every data endpoint below requires the private bearer token.
    nonce = secrets.token_urlsafe(24)
    page = Path(__file__).resolve().parents[1]/'observability/admin.html'
    return HTMLResponse(page.read_text().replace('__NONCE__', nonce), headers={
        'Cache-Control':'private, no-store', 'X-Robots-Tag':'noindex, nofollow',
        'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})


@router.get('/assistant/admin/stats', dependencies=[Depends(_trace_admin)])
async def admin_stats(days:int=Query(default=7, ge=1, le=30), container:Container=Depends(get_container)):
    try:
        return await container.conversations.stats(days)
    except Exception:
        raise HTTPException(503,'Conversation storage unavailable') from None


@router.get('/assistant/admin/turns', dependencies=[Depends(_trace_admin)])
async def admin_turns(limit:int=Query(default=50, ge=1, le=100), before:datetime|None=None,
                      container:Container=Depends(get_container)):
    try:
        turns = await container.conversations.recent(limit, before)
        return {'turns':turns, 'next_before':turns[-1]['started_at'] if len(turns)==limit else None}
    except Exception:
        raise HTTPException(503,'Conversation storage unavailable') from None


@router.get('/assistant/admin/trace/{trace_id}', dependencies=[Depends(_trace_admin)])
async def admin_trace(trace_id:str, container:Container=Depends(get_container)):
    try:
        row = await container.conversations.get(trace_id)
    except Exception:
        raise HTTPException(503,'Conversation storage unavailable') from None
    if row is None:
        raise HTTPException(404,'Trace not found')
    return row


@router.get('/assistant/traces/{trace_id}', dependencies=[Depends(_trace_admin)])
async def trace_detail(trace_id: str, response: Response, container: Container=Depends(get_container)):
    response.headers['Cache-Control']='no-store'
    try:
        result = await container.conversations.get(trace_id)
    except Exception:
        raise HTTPException(503,'Conversation storage unavailable') from None
    if result is None:
        raise HTTPException(404,'Trace not found')
    return result


@router.get('/assistant/conversations/{session_id}', dependencies=[Depends(_trace_admin)])
async def conversation_detail(session_id: str, response: Response, limit: int=Query(default=50,ge=1,le=100),
                              before: datetime | None=None, container: Container=Depends(get_container)):
    response.headers['Cache-Control']='no-store'
    try:
        turns = await container.conversations.session(session_id,limit,before)
    except Exception:
        raise HTTPException(503,'Conversation storage unavailable') from None
    return {'session_id':session_id,'turns':turns,'next_before':turns[-1]['started_at'] if len(turns)==limit else None}


async def _handle(payload: ChatRequest, request: Request, container: Container, on_delta=None) -> ChatResponse:
    memory = ConversationMemory(container.cache) if payload.session_id else None
    history = None
    if memory:
        try:
            async with asyncio.timeout(.15):
                history = await memory.load(payload.session_id)
        except TimeoutError:
            logger.warning('conversation_memory_read_timeout')
    english = payload.language == 'en'
    try:
        async with container.llm_gate.slot(degraded=getattr(request.state, "rate_limited", False)) as full:
            if not full:
                # Lightweight lane: swap in the cheapest model for answering and web research.
                s = container.settings
                container = copy.copy(container)
                container.settings = dataclasses.replace(s, model=s.fallback_model, web_search_model=s.fallback_model)
            response = await _chat(payload, container, history, on_delta)
            response.degraded = not full
    except TimeoutError as exc:
        raise HTTPException(503, "The assistant is busy. Please try again shortly." if english else "毛孩助手而家好多人用，請稍後再試。",
                            headers={"Retry-After": "5"}) from exc
    if memory and response.answer != blocked_reply(payload.language):
        try:
            async with asyncio.timeout(.15):
                await memory.append(payload.session_id, payload.message, response.answer)
        except TimeoutError:
            logger.warning('conversation_memory_write_timeout')
    return response


async def _chat(payload: ChatRequest, container: Container, memory_history: list[dict] | None, on_delta=None) -> ChatResponse:
    english = payload.language == 'en'
    settings = container.settings
    history=memory_history or [item.model_dump() for item in payload.history]
    quick=await fast_answer(payload.message,history,_access(container),payload.language)
    if quick:
        return ChatResponse(**quick,model='saved-data')
    if not settings.api_key or not settings.model:
        raise HTTPException(status_code=503, detail="The assistant is not configured yet. Set the model API key in the backend .env file." if english else "毛孩助手未設定模型密鑰，請喺後端 .env 設定。")
    if not settings.intent_model:
        raise HTTPException(503, 'Intent classifier model is not configured.' if english else '意圖分類模型未設定。')
    if payload.origin and is_simple_nearby(payload.message):
        try:
            value = await _nearby_featured(container, payload.origin, payload.language)
            return ChatResponse(answer=value['answer'], model='featured-cache', places=value['places'], sources=value.get('sources',[]))
        except Exception:
            logger.exception('Featured nearby lookup failed; using the assistant')
    history=memory_history or [item.model_dump() for item in payload.history]
    try:
        async with asyncio.timeout(settings.intent_timeout_seconds):
            decision=await classify_intent(payload.message,api_key=settings.api_key,base_url=settings.base_url,
                model=settings.intent_model,history=history,timeout_seconds=settings.intent_timeout_seconds)
    except Exception as exc:
        # Fail closed: provider/parse errors never bypass the gate or call the main model.
        logger.warning('Intent classifier unavailable (%s)',type(exc).__name__)
        raise HTTPException(503, 'Intent classification is temporarily unavailable. Please try again.' if english else '暫時未能辨識查詢意圖，請稍後再試。') from exc
    action=route_action(decision,settings.intent_confidence_threshold)
    routing=IntentRouting(**decision.model_dump(),action=action,classifier_model=settings.intent_model)
    if action=='self_intro':
        return ChatResponse(answer=assistant_intro_reply(payload.language),model=settings.intent_model,routing=routing)
    web_service=WebKnowledgeService(settings)
    if action=='web_agent':
        result=await web_service.search(payload.message,payload.language,history,decision)
        if result['status']=='unavailable':raise HTTPException(503,result['answer'])
        return ChatResponse(answer=result['answer'],model=settings.web_search_model,routing=routing,sources=result['sources'])
    if action!='main_agent':
        return ChatResponse(answer=gate_reply(action,payload.language),model=settings.intent_model,routing=routing)
    if decision.intent == 'map_query' and decision.map_mode == 'general':
        direct = saved_lookup(payload.message, history, _access(container), payload.language)
        if direct:
            return ChatResponse(**direct, model='saved-data', routing=routing)
    try:
        async with asyncio.timeout(120):
            access = _access(container,(payload.origin.latitude,payload.origin.longitude) if payload.origin else None)
            answer = await run_pet_assistant(
                payload.message, api_key=settings.api_key, base_url=settings.base_url,
                model=settings.model, access=access,
                tool_transport=settings.agent_tool_transport, language=payload.language,
                history=history,intent=decision,web_knowledge=web_service,
                reasoning_effort=settings.main_reasoning_effort,on_delta=on_delta)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="The assistant timed out. Please try again." if english else "毛孩助手回覆逾時，請稍後再試。") from exc
    except Exception as exc:
        logger.exception("Assistant request failed")
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable. Please try again." if english else "毛孩助手暫時答唔到，請稍後再試。") from exc
    sources=list({s['url']:s for s in [*web_service.sources,*access.direction_sources,*access.lookup_sources.values()]}.values())
    # Map answers are grounded in tool data and the intent gate already scoped them; the small review model rejects them too often.
    approved=decision.intent=='map_query' or await review_answer(query=payload.message,answer=answer,intent=decision.intent,map_mode=decision.map_mode,
        api_key=settings.api_key,base_url=settings.base_url,model=settings.intent_model,history=history,
        sources=sources,timeout_seconds=min(settings.intent_timeout_seconds,15))
    if not approved:
        return ChatResponse(answer=blocked_reply(payload.language),model=settings.intent_model,routing=routing)
    return ChatResponse(answer=answer, model=settings.model,routing=routing,sources=sources,places=access.mentioned_places(answer))
