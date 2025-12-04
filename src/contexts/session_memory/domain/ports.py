"""
Session Memory Domain Ports

세션 메모리 도메인의 포트 인터페이스
"""

from typing import Protocol

from .models import Memory, MemoryType, Session


class MemoryStorePort(Protocol):
    """메모리 저장소 포트"""

    async def save(self, memory: Memory) -> None:
        """메모리 저장"""
        ...

    async def get(self, memory_id: str) -> Memory | None:
        """메모리 조회"""
        ...

    async def get_by_session(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> list[Memory]:
        """세션의 메모리 조회"""
        ...

    async def search(
        self,
        query: str,
        session_id: str | None = None,
        memory_type: MemoryType | None = None,
        limit: int = 10,
    ) -> list[Memory]:
        """메모리 검색"""
        ...

    async def delete(self, memory_id: str) -> None:
        """메모리 삭제"""
        ...


class SessionStorePort(Protocol):
    """세션 저장소 포트"""

    async def create(self, session: Session) -> None:
        """세션 생성"""
        ...

    async def get(self, session_id: str) -> Session | None:
        """세션 조회"""
        ...

    async def update(self, session: Session) -> None:
        """세션 업데이트"""
        ...

    async def get_by_repo(self, repo_id: str, limit: int = 10) -> list[Session]:
        """레포지토리의 세션 조회"""
        ...


class EmbeddingProviderPort(Protocol):
    """임베딩 제공자 포트"""

    @property
    def dimension(self) -> int:
        """임베딩 차원"""
        ...

    async def embed(self, text: str) -> list[float]:
        """텍스트 임베딩"""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩"""
        ...
