import asyncio
import copy
import dataclasses
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent.data.data_access import PetDataAccess
from agent.assembly.service import run_pet_assistant
from agent.subagents.web_knowledge import WebKnowledgeService,DOMAINS
from agent.subagents.intent_router import classify_intent, route_action, gate_reply, assistant_intro_reply
from agent.subagents.answer_guard import review_answer, blocked_reply
from agent.data.tools.pet_data import make_pet_queries
from agent.memory.conversation import ConversationMemory
from agent.data.featured_answer import is_simple_nearby, render_nearby
from backend.app.config.container import Container
from backend.app.config.dependencies import get_container
from backend.app.models.assistant import ChatOrigin, ChatRequest, ChatResponse, IntentRouting, PrefillRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["assistant"])


def _access(container: Container, origin=None) -> PetDataAccess:
    return PetDataAccess(container.pets,origin=origin)


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
    data = container.pets.places(mode='restaurants')
    version = data['fetched_at'] or ''
    key = f"nearby:{version}:{language}:{origin.latitude:.3f}:{origin.longitude:.3f}"
    cached = await container.cache.get_json(key)
    if cached:
        return cached
    await asyncio.to_thread(container.featured.ensure, data['items'], version)
    rows = await asyncio.to_thread(container.featured.nearest, origin.latitude, origin.longitude, NEARBY_LIMIT)
    value = {'answer': render_nearby(rows, language), 'places': [{'id': r['id'], 'name': r['name']} for r in rows]}
    await container.cache.set_json(key, value, NEARBY_TTL_SECONDS)
    return value


@router.post("/assistant/prefill")
async def prefill(payload: PrefillRequest, container: Container = Depends(get_container)) -> dict:
    """Warm the nearby-answer cache when the user shares a location."""
    value = await _nearby_featured(container, ChatOrigin(latitude=payload.latitude, longitude=payload.longitude), payload.language)
    return {"cached": True, "count": len(value['places'])}


@router.post("/assistant/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, container: Container = Depends(get_container)) -> ChatResponse:
    return await _handle(payload, request, container)


@router.post("/assistant/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request, container: Container = Depends(get_container)) -> StreamingResponse:
    """Server-sent events: `delta` text chunks as the model writes, then one `final` (or `error`) event.

    The final event arrives after the answer review and replaces the streamed text if it was blocked.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def on_delta(text: str) -> None:
        await queue.put({"type": "delta", "text": text})

    async def work() -> None:
        try:
            response = await _handle(payload, request, container, on_delta)
            await queue.put({"type": "final", **response.model_dump()})
        except HTTPException as exc:
            await queue.put({"type": "error", "status": exc.status_code, "detail": exc.detail})
        except Exception:
            logger.exception("Streaming assistant request failed")
            await queue.put({"type": "error", "status": 500, "detail": "The assistant is temporarily unavailable. Please try again."})
        await queue.put(None)

    task = asyncio.create_task(work())

    async def events():
        try:
            while (item := await queue.get()) is not None:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _handle(payload: ChatRequest, request: Request, container: Container, on_delta=None) -> ChatResponse:
    memory = ConversationMemory(container.cache) if payload.session_id else None
    history = await memory.load(payload.session_id) if memory else None
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
        await memory.append(payload.session_id, payload.message, response.answer)
    return response


async def _chat(payload: ChatRequest, container: Container, memory_history: list[dict] | None, on_delta=None) -> ChatResponse:
    english = payload.language == 'en'
    settings = container.settings
    if not settings.api_key or not settings.model:
        raise HTTPException(status_code=503, detail="The assistant is not configured yet. Set the model API key in the backend .env file." if english else "毛孩助手未設定模型密鑰，請喺後端 .env 設定。")
    if not settings.intent_model:
        raise HTTPException(503, 'Intent classifier model is not configured.' if english else '意圖分類模型未設定。')
    if payload.origin and is_simple_nearby(payload.message):
        try:
            value = await _nearby_featured(container, payload.origin, payload.language)
            return ChatResponse(answer=value['answer'], model='featured-cache', places=value['places'])
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
    sources=web_service.sources+access.direction_sources
    # Map answers are grounded in tool data and the intent gate already scoped them; the small review model rejects them too often.
    approved=decision.intent=='map_query' or await review_answer(query=payload.message,answer=answer,intent=decision.intent,map_mode=decision.map_mode,
        api_key=settings.api_key,base_url=settings.base_url,model=settings.intent_model,history=history,
        sources=sources,timeout_seconds=min(settings.intent_timeout_seconds,15))
    if not approved:
        return ChatResponse(answer=blocked_reply(payload.language),model=settings.intent_model,routing=routing)
    return ChatResponse(answer=answer, model=settings.model,routing=routing,sources=sources,places=access.mentioned_places(answer))
