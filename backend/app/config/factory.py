"""Application factory: routers are supplied by the outermost main.py."""
from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

from backend.app.config.lifespan import lifespan
from backend.app.config.middleware import register_middleware
from backend.app.config.settings import Settings, get_settings


def create_app(routers: Iterable[APIRouter], settings: Settings | None = None,
               api_prefix: str = "/api/v1") -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="HK PetFinder API", version="0.2.0", lifespan=lifespan)
    register_middleware(app, settings, api_prefix)
    for router in routers:
        app.include_router(router, prefix=api_prefix)
    return app
