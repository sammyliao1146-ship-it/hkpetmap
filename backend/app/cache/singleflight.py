"""Coalesce overlapping reads without sharing results beyond the request's lifetime."""
import asyncio


class SingleFlight:
    def __init__(self, capacity=64):
        self.capacity = capacity
        self.pending = {}

    async def run(self, key, factory):
        task = self.pending.get(key)
        if task is None:
            if len(self.pending) >= self.capacity:
                return await factory()
            task = asyncio.create_task(factory())
            self.pending[key] = task
            def done(completed):
                if self.pending.get(key) is completed:
                    self.pending.pop(key, None)
                if not completed.cancelled():
                    completed.exception()
            task.add_done_callback(done)
        return await asyncio.shield(task)

    async def aclose(self):
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
