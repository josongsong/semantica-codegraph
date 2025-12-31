"""
Multi Index DI Container (테스트 전용)

테스트용 FakeIndex 기반 컨테이너입니다.
프로덕션에서는 infrastructure.di.IndexContainer를 사용하세요.

Usage (테스트):
    from codegraph_engine.multi_index.di import multi_index_container
    container = multi_index_container  # FakeIndex 기반

Usage (프로덕션):
    from src.container import container
    index_container = container._index  # 또는 container.contexts.multi_index
"""

from functools import cached_property

from .domain.models import IndexType
from .infrastructure.fake_index import FakeIndex
from .usecase.upsert_to_index import UpsertToIndexUseCase


class MultiIndexContainer:
    """
    Multi Index BC의 DI Container (테스트용 FakeIndex 기반).

    프로덕션에서는 IndexContainer (infrastructure/di.py)를 사용하세요.
    """

    @cached_property
    def lexical_index(self) -> FakeIndex:
        """Lexical 인덱스 (FakeIndex)"""
        return FakeIndex(IndexType.LEXICAL)

    @cached_property
    def vector_index(self) -> FakeIndex:
        """Vector 인덱스 (FakeIndex)"""
        return FakeIndex(IndexType.VECTOR)

    @cached_property
    def symbol_index(self) -> FakeIndex:
        """Symbol 인덱스 (FakeIndex)"""
        return FakeIndex(IndexType.SYMBOL)

    @cached_property
    def fuzzy_index(self) -> FakeIndex:
        """Fuzzy 인덱스 (FakeIndex)"""
        return FakeIndex(IndexType.FUZZY)

    @cached_property
    def upsert_to_lexical_usecase(self) -> UpsertToIndexUseCase:
        """Lexical 인덱스 업서트 UseCase"""
        return UpsertToIndexUseCase(self.lexical_index, IndexType.LEXICAL)

    @cached_property
    def upsert_to_vector_usecase(self) -> UpsertToIndexUseCase:
        """Vector 인덱스 업서트 UseCase"""
        return UpsertToIndexUseCase(self.vector_index, IndexType.VECTOR)

    @cached_property
    def upsert_to_symbol_usecase(self) -> UpsertToIndexUseCase:
        """Symbol 인덱스 업서트 UseCase"""
        return UpsertToIndexUseCase(self.symbol_index, IndexType.SYMBOL)


# 테스트용 전역 싱글톤
multi_index_container = MultiIndexContainer()
