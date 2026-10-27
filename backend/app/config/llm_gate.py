"""Process-wide cap on concurrent LLM chat requests, with a lightweight-model lane for overflow."""
import asyncio
from contextlib import asynccontextmanager


class LLMGate:
    def __init__(self, max_concurrency: int, fallback_concurrency: int, queue_timeout: float) -> None:
        self._full = asyncio.Semaphore(max_concurrency)
        self._light = asyncio.Semaphore(fallback_concurrency)
        self.queue_timeout = queue_timeout

    @asynccontextmanager
    async def slot(self, degraded: bool = False):
        """Yield True when running on the full model, False on the lightweight fallback.

        Raises TimeoutError when even the fallback lane is saturated.
        """
        if not degraded:
            try:
                await asyncio.wait_for(self._full.acquire(), self.queue_timeout)
            except TimeoutError:
                degraded = True
            else:
                try:
                    yield True
                finally:
                    self._full.release()
                return
        await asyncio.wait_for(self._light.acquire(), self.queue_timeout)
        try:
            yield False
        finally:
            self._light.release()
