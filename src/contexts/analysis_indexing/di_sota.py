"""
SOTA DI Container

DDD + Hexagonal + CQRS 아키텍처를 위한 의존성 주입 컨테이너
"""

from functools import cached_property

from .application.handlers.index_repository_handler import IndexRepositoryHandler
from .application.handlers.session_query_handler import SessionQueryHandler
from .infrastructure.event_bus.in_memory_event_bus import InMemoryEventBus
from .infrastructure.repositories.in_memory_session_repository import InMemorySessionRepository


class AnalysisIndexingContainerSOTA:
    """SOTA급 Analysis Indexing DI Container"""

    def __init__(
        self,
        parser_registry=None,
        ir_generator=None,
        graph_builder=None,
        chunk_builder=None,
        graph_store=None,
        chunk_store=None,
        lexical_index=None,
        vector_index=None,
    ):
        """
        초기화

        Args:
            parser_registry: Parser Registry (선택)
            ir_generator: IR Generator (선택)
            graph_builder: Graph Builder (선택)
            chunk_builder: Chunk Builder (선택)
            graph_store: Graph Store (선택)
            chunk_store: Chunk Store (선택)
            lexical_index: Lexical Index (선택)
            vector_index: Vector Index (선택)
        """
        self._parser_registry = parser_registry
        self._ir_generator = ir_generator
        self._graph_builder = graph_builder
        self._chunk_builder = chunk_builder
        self._graph_store = graph_store
        self._chunk_store = chunk_store
        self._lexical_index = lexical_index
        self._vector_index = vector_index

    # Domain Layer - Repositories

    @cached_property
    def session_repository(self) -> InMemorySessionRepository:
        """세션 리포지토리"""
        return InMemorySessionRepository()

    # Infrastructure Layer - Event Bus

    @cached_property
    def event_bus(self) -> InMemoryEventBus:
        """이벤트 버스"""
        return InMemoryEventBus()

    # Infrastructure Layer - Adapters

    @cached_property
    def file_processor(self):
        """파일 처리 어댑터"""
        from .infrastructure.adapters.processors.file_processor import FileProcessorAdapter

        if not self._parser_registry:
            from src.contexts.code_foundation.infrastructure.parsing.parser_registry import get_registry

            self._parser_registry = get_registry()

        return FileProcessorAdapter(self._parser_registry)

    @cached_property
    def ir_generator_adapter(self):
        """IR 생성 어댑터"""
        from .infrastructure.adapters.generators.ir_generator_adapter import IRGeneratorAdapter

        if not self._ir_generator:
            from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator

            self._ir_generator = PythonIRGenerator(repo_id="default")

        return IRGeneratorAdapter(self._ir_generator, None)

    @cached_property
    def graph_builder_adapter(self):
        """그래프 빌더 어댑터"""
        from .infrastructure.adapters.generators.graph_builder_adapter import GraphBuilderAdapter

        if not self._graph_builder:
            from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder

            self._graph_builder = GraphBuilder()

        return GraphBuilderAdapter(self._graph_builder)

    @cached_property
    def chunk_builder_adapter(self):
        """청크 빌더 어댑터"""
        from .infrastructure.adapters.generators.chunk_builder_adapter import ChunkBuilderAdapter

        if not self._chunk_builder:
            from src.contexts.code_foundation.infrastructure.chunk.builder import ChunkBuilder
            from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator

            self._chunk_builder = ChunkBuilder(id_generator=ChunkIdGenerator())

        return ChunkBuilderAdapter(self._chunk_builder)

    @cached_property
    def graph_storage_adapter(self):
        """그래프 저장소 어댑터"""
        from .infrastructure.adapters.storage.graph_storage_adapter import GraphStorageAdapter

        return GraphStorageAdapter(self._graph_store)

    @cached_property
    def chunk_storage_adapter(self):
        """청크 저장소 어댑터"""
        from .infrastructure.adapters.storage.chunk_storage_adapter import ChunkStorageAdapter

        return ChunkStorageAdapter(self._chunk_store)

    @cached_property
    def lexical_index_adapter(self):
        """렉시컬 인덱스 어댑터"""
        from .infrastructure.adapters.storage.index_adapter import LexicalIndexAdapter

        return LexicalIndexAdapter(self._lexical_index)

    @cached_property
    def vector_index_adapter(self):
        """벡터 인덱스 어댑터"""
        from .infrastructure.adapters.storage.index_adapter import VectorIndexAdapter

        return VectorIndexAdapter(self._vector_index)

    # Application Layer - CQRS Handlers

    @cached_property
    def index_repository_handler(self) -> IndexRepositoryHandler:
        """리포지토리 인덱싱 명령 처리기 (CQRS Command Handler)"""
        return IndexRepositoryHandler(
            session_repository=self.session_repository,
            file_processor=self.file_processor,
            ir_generator=self.ir_generator_adapter,
            graph_builder=self.graph_builder_adapter,
            chunk_builder=self.chunk_builder_adapter,
            graph_storage=self.graph_storage_adapter,
            chunk_storage=self.chunk_storage_adapter,
            lexical_index=self.lexical_index_adapter,
            vector_index=self.vector_index_adapter,
        )

    @cached_property
    def session_query_handler(self) -> SessionQueryHandler:
        """세션 조회 쿼리 처리기 (CQRS Query Handler)"""
        return SessionQueryHandler(session_repository=self.session_repository)


# 전역 싱글톤
analysis_indexing_container_sota = AnalysisIndexingContainerSOTA()
