"""
Multi Index DI Container

다중 인덱스 컨텍스트의 의존성 주입 컨테이너
"""

from functools import cached_property

from .domain.models import IndexType
from .infrastructure.fake_index import FakeIndex
from .usecase.upsert_to_index import UpsertToIndexUseCase


class MultiIndexContainer:
    """Multi Index BC의 DI Container"""

    @cached_property
    def lexical_index(self) -> FakeIndex:
        """Lexical 인덱스"""
        return FakeIndex(IndexType.LEXICAL)

    @cached_property
    def vector_index(self) -> FakeIndex:
        """Vector 인덱스"""
        return FakeIndex(IndexType.VECTOR)

    @cached_property
    def symbol_index(self) -> FakeIndex:
        """Symbol 인덱스"""
        return FakeIndex(IndexType.SYMBOL)

    @cached_property
    def fuzzy_index(self) -> FakeIndex:
        """Fuzzy 인덱스"""
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


# 전역 싱글톤
multi_index_container = MultiIndexContainer()
