"""FastAPI dependency getters that read the container built by the lifespan."""
from fastapi import Request

from backend.app.config.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container
