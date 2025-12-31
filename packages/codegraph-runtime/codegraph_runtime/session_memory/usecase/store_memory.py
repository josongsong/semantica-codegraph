"""
Store Memory UseCase
"""

from ..domain.models import Memory
from ..ports import MemoryStorePort


class StoreMemoryUseCase:
    """메모리 저장 UseCase"""

    def __init__(self, memory_store: MemoryStorePort):
        self.memory_store = memory_store

    async def execute(self, memory: Memory) -> None:
        """메모리 저장"""
        await self.memory_store.store(memory)
