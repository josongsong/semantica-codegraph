"""Python Complex: Async/Await Patterns"""

import asyncio
from collections.abc import AsyncIterator


async def async_function(x: int) -> int:
    """Simple async function"""
    await asyncio.sleep(0.1)
    return x * 2


async def async_with_multiple_awaits(items: list[int]) -> list[int]:
    """Multiple await calls"""
    results = []
    for item in items:
        result = await async_function(item)
        results.append(result)
    return results


async def async_generator() -> AsyncIterator[int]:
    """Async generator"""
    for i in range(5):
        await asyncio.sleep(0.1)
        yield i


class AsyncContext:
    """Async context manager"""

    async def __aenter__(self):
        await asyncio.sleep(0.1)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await asyncio.sleep(0.1)
        return False


async def use_async_context():
    """Using async context manager"""
    async with AsyncContext():
        result = await async_function(42)
        return result
