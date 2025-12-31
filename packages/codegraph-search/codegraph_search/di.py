"""
Retrieval Search DI Container

검색 컨텍스트의 의존성 주입 컨테이너
"""

import os
from functools import cached_property

from .infrastructure.fake_search_engine import FakeSearchEngine
from .infrastructure.retriever_adapter import RetrieverAdapter
from .usecase.search_code import SearchCodeUseCase


class RetrievalSearchContainer:
    """Retrieval Search BC의 DI Container"""

    def __init__(self, use_fake: bool = False):
        """
        초기화

        Args:
            use_fake: Fake 구현 사용 여부
        """
        self._use_fake = use_fake or os.getenv("USE_FAKE_STORES", "false").lower() == "true"

    @cached_property
    def search_engine(self):
        """검색 엔진"""
        if self._use_fake:
            return FakeSearchEngine()

        # 실제 RetrieverServiceV3 사용
        from src.container import container

        return RetrieverAdapter(retriever_service=container.retriever_v3_service)

    @cached_property
    def search_code_usecase(self) -> SearchCodeUseCase:
        """코드 검색 UseCase"""
        return SearchCodeUseCase(
            search_engine=self.search_engine,
        )


# 전역 싱글톤
retrieval_search_container = RetrievalSearchContainer()
