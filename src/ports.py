"""
Semantica Code Engine Ports

server 계층이 호출할 인터페이스 정의
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol


class IndexingPort(Protocol):
    """인덱싱 포트"""

    @abstractmethod
    def index_repository(self, repo_path: str, **options) -> dict[str, Any]:
        """저장소 인덱싱"""
        ...

    @abstractmethod
    def get_indexing_status(self, repo_id: str) -> dict[str, Any]:
        """인덱싱 상태 조회"""
        ...


class SearchPort(Protocol):
    """검색 포트"""

    @abstractmethod
    def search(self, query: str, **options) -> list[dict[str, Any]]:
        """코드 검색"""
        ...

    @abstractmethod
    def search_symbols(self, symbol_name: str, **options) -> list[dict[str, Any]]:
        """심볼 검색"""
        ...

    @abstractmethod
    def search_chunks(self, query: str, **options) -> list[dict[str, Any]]:
        """청크 검색"""
        ...


class GraphPort(Protocol):
    """그래프 포트"""

    @abstractmethod
    def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """호출자 조회"""
        ...

    @abstractmethod
    def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """피호출자 조회"""
        ...

    @abstractmethod
    def get_dependencies(self, node_id: str) -> list[dict[str, Any]]:
        """의존성 조회"""
        ...


class ContextPort(Protocol):
    """컨텍스트 포트"""

    @abstractmethod
    def build_context(self, query: str, **options) -> str:
        """컨텍스트 생성"""
        ...

    @abstractmethod
    def get_repomap(self, repo_id: str, **options) -> str:
        """레포맵 조회"""
        ...


class EnginePort(IndexingPort, SearchPort, GraphPort, ContextPort, Protocol):
    """
    통합 엔진 포트

    server 계층이 사용할 전체 인터페이스
    """

    pass
