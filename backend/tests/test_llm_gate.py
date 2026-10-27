import asyncio
import pytest
from backend.app.config.llm_gate import LLMGate


def test_overflow_degrades_then_rejects():
    asyncio.run(_overflow())


async def _overflow():
    gate = LLMGate(1, 1, 0.05)
    async with gate.slot() as a:
        assert a is True
        async with gate.slot() as b:
            assert b is False
            with pytest.raises(TimeoutError):
                async with gate.slot():
                    pass


def test_forced_degrade_and_release():
    asyncio.run(_forced())


async def _forced():
    gate = LLMGate(1, 1, 0.05)
    async with gate.slot(degraded=True) as full:
        assert full is False
    async with gate.slot() as full:
        assert full is True
