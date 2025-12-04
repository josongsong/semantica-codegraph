"""
Code Foundation DI Container

코드 분석 파이프라인의 의존성 주입 컨테이너
"""

import os
from functools import cached_property

from .usecase.parse_file import ParseFileUseCase
from .usecase.process_file import ProcessFileUseCase


class CodeFoundationContainer:
    """Code Foundation BC의 DI Container"""

    def __init__(self, use_fake: bool = False):
        """
        초기화

        Args:
            use_fake: Fake 구현 사용 여부
        """
        self._use_fake = use_fake or os.getenv("USE_FAKE_STORES", "false").lower() == "true"

    @cached_property
    def parser(self):
        """AST 파서"""
        if self._use_fake:
            from .infrastructure.fake_parser import FakeParser

            return FakeParser()

        # 실제 foundation parser 사용
        from src.contexts.code_foundation.infrastructure.parsing.parser_registry import get_registry

        from .infrastructure.foundation_adapter import FoundationParserAdapter

        return FoundationParserAdapter(parser_registry=get_registry())

    @cached_property
    def ir_generator(self):
        """IR 생성기

        Note: 도메인 UseCase 테스트용 간단한 IR 생성기입니다.
        실제 인덱싱 파이프라인에서는 IndexingContainer를 통해
        PythonIRGenerator를 직접 사용합니다.
        (src/contexts/analysis_indexing/infrastructure/di.py 참조)
        """
        # 도메인 UseCase 테스트용 Fake 구현
        # 실제 IR 생성은 analysis_indexing 컨텍스트에서 수행
        from .infrastructure.fake_ir_generator import FakeIRGenerator

        return FakeIRGenerator()

    @cached_property
    def graph_builder(self):
        """그래프 빌더"""
        if self._use_fake:
            from .infrastructure.fake_graph_builder import FakeGraphBuilder

            return FakeGraphBuilder()

        # 실제 foundation graph builder 사용
        from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder

        from .infrastructure.foundation_adapter import FoundationGraphBuilderAdapter

        return FoundationGraphBuilderAdapter(graph_builder=GraphBuilder())

    @cached_property
    def chunker(self):
        """청커"""
        if self._use_fake:
            from .infrastructure.fake_chunker import FakeChunker

            return FakeChunker()

        # 실제 foundation chunker 사용
        from src.contexts.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator

        from .infrastructure.foundation_adapter import FoundationChunkerAdapter

        id_gen = ChunkIdGenerator()
        return FoundationChunkerAdapter(chunk_builder=ChunkBuilder(id_generator=id_gen))

    @cached_property
    def parse_file_usecase(self) -> ParseFileUseCase:
        """파일 파싱 UseCase"""
        return ParseFileUseCase(parser=self.parser)

    @cached_property
    def process_file_usecase(self) -> ProcessFileUseCase:
        """파일 전체 처리 UseCase"""
        return ProcessFileUseCase(
            parser=self.parser,
            ir_generator=self.ir_generator,
            graph_builder=self.graph_builder,
            chunker=self.chunker,
        )


# 전역 싱글톤
code_foundation_container = CodeFoundationContainer()
