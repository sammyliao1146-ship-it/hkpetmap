"""Web processes read published snapshots; they never fetch upstream datasets."""
import asyncio
import logging
from contextlib import asynccontextmanager,suppress
from fastapi import FastAPI
from backend.app.config.container import build_container
from backend.app.config.settings import get_settings
from backend.app.observability.store import ConversationStore
import os

async def snapshot_reader(container):
    while True:
        try:
            await container.pets.reload_if_changed()
        except Exception:
            logging.getLogger(__name__).exception('Snapshot reload failed; keeping the last loaded data')
        await asyncio.sleep(container.settings.snapshot_poll_seconds)

async def warm_conversations(container):
    # Opening the pool and schema is not charged to the first user's response.
    store = getattr(container, 'conversations', None)
    if not isinstance(store, ConversationStore):
        return
    try:
        async with asyncio.timeout(8):
            await store.initialize()
    except Exception as exc:
        logging.getLogger(__name__).warning('Conversation pool warmup failed: %s', type(exc).__name__)

async def warm_photos():
    if os.getenv('PHOTO_PREGENERATE', 'true').lower() not in {'true', '1'}:
        return
    from scripts.build_photo_variants import photo_paths
    from backend.app.services.photo_service import prepare_variants
    # One photo at a time, yielding between files; HTTP resize concurrency remains bounded.
    for path in photo_paths():
        try:
            await asyncio.to_thread(prepare_variants, path)
        except OSError as exc:
            logging.getLogger(__name__).warning('Photo preparation failed: %s', type(exc).__name__)
        await asyncio.sleep(.02)

@asynccontextmanager
async def lifespan(app:FastAPI):
    owned = not getattr(app.state,'container',None)
    container=getattr(app.state,'container',None) or await build_container(get_settings())
    app.state.container=container
    reader=asyncio.create_task(snapshot_reader(container),name='pet-snapshot-reader')
    warmer=asyncio.create_task(warm_conversations(container),name='conversation-pool-warmup')
    photos=asyncio.create_task(warm_photos(),name='local-photo-variants') if owned else None
    try:
        yield
    finally:
        reader.cancel()
        with suppress(asyncio.CancelledError):await reader
        warmer.cancel()
        with suppress(asyncio.CancelledError):await warmer
        if photos:
            photos.cancel()
            with suppress(asyncio.CancelledError):await photos
        await container.aclose()
