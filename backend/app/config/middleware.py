"""HTTP middleware: CORS, gzip, request id + access log, chat rate limit."""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from backend.app.config.settings import Settings
from backend.app.config.request_security import is_secret_probe

logger = logging.getLogger("hkpet.access")
RATE_LIMITED_PATHS = ("/assistant/chat", "/assistant/chat/stream", "/assistant/prefill", "/plans")


def register_middleware(app: FastAPI, settings: Settings, api_prefix: str) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        container = getattr(request.app.state, "container", None)
        path = request.url.path
        raw_path = request.scope.get('raw_path', b'').decode('latin-1') or path
        if is_secret_probe(raw_path):
            return JSONResponse({'detail':'Not found'}, status_code=404,
                                headers={'Cache-Control':'private, no-store',
                                         'X-Content-Type-Options':'nosniff', 'X-Request-ID':request_id})
        if container and request.method == "POST" and path.startswith(api_prefix) \
                and path[len(api_prefix):] in RATE_LIMITED_PATHS:
            client = request.client.host if request.client else "unknown"
            count = await container.cache.hit(f"rate:{client}:{path}", settings.chat_rate_window_seconds)
            if count > settings.chat_rate_hard_limit:
                return JSONResponse({"detail": "問得太密喇，請稍後再試。"}, status_code=429,
                                    headers={"Retry-After": str(settings.chat_rate_window_seconds),
                                             "X-RateLimit-Limit": str(settings.chat_rate_hard_limit),
                                             "X-RateLimit-Remaining": "0", "X-Request-ID": request_id})
            # Over the soft limit: still answer, but the router downgrades to the lightweight model.
            request.state.rate_limited = count > settings.chat_rate_limit
        response = await call_next(request)
        # Dynamic/private content never enters a shared CDN cache, including errors.
        api_path=path[len(api_prefix):] if path.startswith(api_prefix) else ''
        if response.status_code>=400 or request.method!='GET' or api_path.startswith(('/assistant/','/plans','/places')):
            if 'no-store' not in response.headers.get('cache-control',''):
                response.headers['Cache-Control']='private, no-store'
        elif 'cache-control' not in response.headers:
            if api_path=='/activities':response.headers['Cache-Control']='public, max-age=0, s-maxage=60'
            elif api_path=='/parking' and 'latitude' not in request.query_params and 'longitude' not in request.query_params:
                response.headers['Cache-Control']='public, max-age=0, s-maxage=30'
            else:response.headers['Cache-Control']='private, no-store'
        if request.headers.get('authorization') or request.headers.get('cookie'):
            if 'no-store' not in response.headers.get('cache-control',''):
                response.headers['Cache-Control']='private, no-store'
        response.headers["X-Request-ID"] = request_id
        logger.info("%s %s -> %s [%s]", request.method, path, response.status_code, request_id)
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    origins = list(dict.fromkeys([*settings.cors_origins, 'https://hkpetmap.com', 'https://www.hkpetmap.com']))
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
                       expose_headers=["X-Request-ID"])
