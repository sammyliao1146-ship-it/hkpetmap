"""Web processes read published snapshots; they never fetch upstream datasets."""
import asyncio
import logging
from contextlib import asynccontextmanager,suppress
from fastapi import FastAPI
from backend.app.config.container import build_container
from backend.app.config.settings import get_settings

async def snapshot_reader(container):
    while True:
        try:
            await container.pets.reload_if_changed()
        except Exception:
            logging.getLogger(__name__).exception('Snapshot reload failed; keeping the last loaded data')
        await asyncio.sleep(container.settings.snapshot_poll_seconds)

@asynccontextmanager
async def lifespan(app:FastAPI):
    container=getattr(app.state,'container',None) or await build_container(get_settings())
    app.state.container=container
    reader=asyncio.create_task(snapshot_reader(container),name='pet-snapshot-reader')
    try:
        yield
    finally:
        reader.cancel()
        with suppress(asyncio.CancelledError):await reader
        await container.aclose()
