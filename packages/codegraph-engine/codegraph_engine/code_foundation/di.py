"""
Code Foundation DI Container

코드 분석 파이프라인의 의존성 주입 컨테이너
"""

import os
from functools import cached_property

from .application.parse_file import ParseFileUseCase
from .application.process_file import ProcessFileUseCase
from .domain.query.types import AnalyzerMode


class CodeFoundationContainer:
    """Code Foundation BC의 DI Container"""

    def __init__(self, use_fake: bool = False, repo_id: str | None = None):
        """
        초기화

        Args:
            use_fake: Fake 구현 사용 여부 (기본값: False - 실제 구현 사용)
            repo_id: Repository ID (기본값: REPO_ID env var 또는 "default")
        """
        # 환경변수로 명시적으로 fake 사용을 요청한 경우에만 fake 사용
        self._use_fake = use_fake and os.getenv("USE_FAKE_STORES", "false").lower() == "true"
        self._repo_id = repo_id or os.getenv("REPO_ID", "default")

    # ============================================================
    # RFC-024: Analyzer Framework (신규!)
    # ============================================================

    @cached_property
    def analyzer_registry(self):
        """
        Analyzer Registry (RFC-024)

        Returns:
            AnalyzerRegistry singleton

        Note:
            Config import → 자동 등록
        """
        # Config import → 자동 등록 트리거!
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs import (
            baseline,  # noqa: F401
            cost,  # noqa: F401 (RFC-028)
        )
        from codegraph_engine.code_foundation.infrastructure.analyzers.registry_v2 import get_registry

        return get_registry()

    def create_analyzer_pipeline(self, ir_doc, mode: AnalyzerMode = AnalyzerMode.REALTIME):
        """
        Analyzer Pipeline 생성 (RFC-024 + RFC-028)

        Args:
            ir_doc: IR Document
            mode: AnalyzerMode.REALTIME | PR | AUDIT | COST

        Returns:
            AnalyzerPipeline

        Usage:
            >>> container = CodeFoundationContainer()
            >>> pipeline = container.create_analyzer_pipeline(ir_doc, mode=AnalyzerMode.REALTIME)
            >>> result = pipeline.run(incremental=True)

            >>> # Cost analysis (RFC-028)
            >>> pipeline = container.create_analyzer_pipeline(ir_doc, mode=AnalyzerMode.COST)
            >>> result = pipeline.run(incremental=False)

        Modes:
            - REALTIME: 증분, <500ms (SCCP만)
            - PR: <5s (SCCP + Taint lite)
            - AUDIT: 분 단위 (SCCP + Taint full + Null + Z3)
            - COST: <1s (SCCP + Cost Analysis, RFC-028)
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs.modes import (
            create_audit_pipeline,
            create_cost_pipeline,
            create_pr_pipeline,
            create_realtime_pipeline,
        )

        if mode == AnalyzerMode.REALTIME:
            return create_realtime_pipeline(ir_doc)
        elif mode == AnalyzerMode.PR:
            return create_pr_pipeline(ir_doc)
        elif mode == AnalyzerMode.AUDIT:
            return create_audit_pipeline(ir_doc)
        elif mode == AnalyzerMode.COST:
            return create_cost_pipeline(ir_doc)
        else:
            raise ValueError(f"Unknown mode: {mode}. Use AnalyzerMode.REALTIME, PR, AUDIT, or COST.")

    @cached_property
    def parser(self):
        """AST 파서"""
        if self._use_fake:
            from tests.fakes.code_foundation.fake_parser import FakeParser

            return FakeParser()

        # 실제 foundation parser 사용
        from codegraph_engine.code_foundation.infrastructure.parsing.parser_registry import get_registry

        from .adapters.foundation_adapters import FoundationParserAdapter

        return FoundationParserAdapter(parser_registry=get_registry())

    @cached_property
    def ir_generator(self):
        """IR 생성기"""
        if self._use_fake:
            from tests.fakes.code_foundation.fake_ir_generator import FakeIRGenerator

            return FakeIRGenerator()

        # 실제 PythonIRGenerator 사용
        from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator

        from .adapters.foundation_adapters import FoundationIRGeneratorAdapter

        # PythonIRGenerator 인스턴스 생성
        python_generator = _PythonIRGenerator(repo_id=self._repo_id)

        return FoundationIRGeneratorAdapter(
            ir_generator=python_generator,
            repo_id=self._repo_id,
        )

    @cached_property
    def graph_builder(self):
        """그래프 빌더"""
        if self._use_fake:
            from tests.fakes.code_foundation.fake_graph_builder import FakeGraphBuilder

            return FakeGraphBuilder()

        # 실제 foundation graph builder 사용
        from codegraph_engine.code_foundation.infrastructure.graph.builder import GraphBuilder

        from .adapters.foundation_adapters import FoundationGraphBuilderAdapter

        return FoundationGraphBuilderAdapter(graph_builder=GraphBuilder())

    @cached_property
    def chunker(self):
        """청커"""
        if self._use_fake:
            from tests.fakes.code_foundation.fake_chunker import FakeChunker

            return FakeChunker()

        # 실제 foundation chunker 사용
        from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
        from codegraph_engine.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator

        from .adapters.foundation_adapters import FoundationChunkerAdapter

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

    # ========================================================================
    # RFC-010: Advanced Taint Analysis
    # ========================================================================

    @cached_property
    def precise_call_graph_builder(self):
        """Precise call graph builder with type narrowing"""
        from codegraph_engine.code_foundation.infrastructure.graphs.precise_call_graph import (
            PreciseCallGraphBuilder,
        )

        return PreciseCallGraphBuilder()

    def create_call_graph_adapter(self, ir_documents: dict):
        """
        Create CallGraphAdapter from IR documents

        Args:
            ir_documents: {file_path: IR document}

        Returns:
            CallGraphAdapter with built call graph

        Raises:
            ValueError: If ir_documents is empty
        """
        if not ir_documents:
            raise ValueError("ir_documents cannot be empty")

        from codegraph_engine.code_foundation.infrastructure.analyzers.call_graph_adapter import (
            CallGraphAdapter,
        )

        builder = self.precise_call_graph_builder
        builder.build_precise_cg(ir_documents)

        return CallGraphAdapter(builder)

    def create_interprocedural_taint_analyzer(
        self,
        call_graph_adapter,
        max_depth: int = 10,
        max_paths: int = 100,
    ):
        """
        Create inter-procedural taint analyzer

        Args:
            call_graph_adapter: CallGraphAdapter instance
            max_depth: Maximum recursion depth
            max_paths: Maximum paths to track

        Returns:
            InterproceduralTaintAnalyzer instance

        Raises:
            TypeError: If call_graph_adapter is invalid
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
            InterproceduralTaintAnalyzer,
        )

        return InterproceduralTaintAnalyzer(
            call_graph=call_graph_adapter,
            max_depth=max_depth,
            max_paths=max_paths,
        )


# 전역 싱글톤
code_foundation_container = CodeFoundationContainer()


# ============================================================
# Startup Hook: Type Config Health Check
# ============================================================


def check_type_config_health_on_startup(
    warn_only: bool = True,
    auto_sync: bool = False,
) -> bool:
    """
    Check type config health at application startup.

    Call this in your application's initialization code to ensure
    type configs are fresh and the Python environment hasn't changed.

    Args:
        warn_only: If True, only log warning (don't block startup)
        auto_sync: If True, automatically sync if configs are stale

    Returns:
        True if healthy or warning mode, False if unhealthy and not warn_only

    Environment Variables:
        SEMANTICA_TYPE_SYNC_CHECK: "false" to disable check entirely
        SEMANTICA_TYPE_SYNC_AUTO: "true" to enable auto-sync
        SEMANTICA_TYPE_SYNC_MAX_AGE_DAYS: Max age before warning (default: 7)

    Usage:
        # In your app startup (e.g., FastAPI lifespan, Django ready)
        from codegraph_engine.code_foundation.di import check_type_config_health_on_startup

        # Option 1: Simple warning (default)
        check_type_config_health_on_startup()

        # Option 2: Auto-sync if stale
        check_type_config_health_on_startup(auto_sync=True)

        # Option 3: Block startup if unhealthy
        if not check_type_config_health_on_startup(warn_only=False):
            raise RuntimeError("Type configs need sync!")
    """
    import logging

    from codegraph_engine.code_foundation.infrastructure.type_inference.sync_health import (
        SyncHealthChecker,
    )

    logger = logging.getLogger(__name__)

    try:
        checker = SyncHealthChecker(auto_sync=auto_sync)
        status = checker.check_and_warn()

        if status.is_healthy:
            logger.debug("Type config health check passed")
            return True

        # Log warning with details
        logger.warning(
            f"Type config health check: {status.message}. Run 'python generate_builtin_types.py --sync-all' to update."
        )

        if warn_only:
            return True

        return False

    except Exception as e:
        logger.warning(f"Type config health check failed: {e}")
        return warn_only  # Don't block on errors if warn_only
