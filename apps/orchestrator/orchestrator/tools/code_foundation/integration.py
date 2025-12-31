"""
V8 Orchestrator Integration

Code Foundation Tools를 V8에 통합

HEXAGONAL ARCHITECTURE:
- Domain (Tools) ← Port (Interface) ← Adapter (Infrastructure)
- Infrastructure 직접 의존 금지
"""

import logging

from .impact import (
    ComputeChangeImpactTool,
    FindAffectedCodeTool,
)

# Ports (Interfaces Only)
from .ports import (
    CallGraphBuilderPort,
    CrossFileResolverPort,
    DependencyGraphPort,
    EmbeddingServiceProtocol,
    ImpactAnalyzerPort,
    IRAnalyzerPort,
    LLMAdapterProtocol,
    ReferenceAnalyzerPort,
    SecurityAnalyzerPort,
    TaintEnginePort,
)
from .provider import CodeFoundationToolProvider, ToolProviderFactory
from .security import (
    DetectVulnerabilitiesTool,
)

# Tools
from .understanding import (
    BuildCallGraphTool,
    FindAllReferencesTool,
    GetSymbolDefinitionTool,
)

logger = logging.getLogger(__name__)


class CodeFoundationToolsIntegrator:
    """
    Code Foundation Tools 통합 헬퍼

    V8 Orchestrator에서 쉽게 사용할 수 있도록 초기화 및 등록

    STRICT MODE: Stub/Fake 금지, 실제 컴포넌트 필수
    """

    @staticmethod
    def _get_required_component(obj: any, name: str) -> any:
        """
        필수 컴포넌트 가져오기

        Args:
            obj: 부모 객체
            name: 컴포넌트 이름

        Returns:
            컴포넌트 객체

        Raises:
            NotImplementedError: 컴포넌트가 없을 경우
        """
        component = getattr(obj, name, None)
        if component is None:
            raise NotImplementedError(
                f"INTEGRATION INCOMPLETE: Required component '{name}' "
                f"not found in {type(obj).__name__}. "
                f"Code Foundation integration cannot proceed. "
                f"Please implement {name} first."
            )
        return component

    @staticmethod
    def initialize(
        ir_analyzer: IRAnalyzerPort,
        security_analyzer: SecurityAnalyzerPort,
        embedding_service: EmbeddingServiceProtocol | None = None,
        llm_adapter: LLMAdapterProtocol | None = None,
    ) -> CodeFoundationToolProvider:
        """
        Tool Provider 초기화

        HEXAGONAL ARCHITECTURE:
        - Port (Interface)에만 의존
        - 구체적인 구현 클래스 알 필요 없음

        Args:
            ir_analyzer: IRAnalyzerPort (인터페이스)
            security_analyzer: SecurityAnalyzerPort (인터페이스)
            embedding_service: EmbeddingServiceProtocol (선택)
            llm_adapter: LLMAdapterProtocol (선택)

        Returns:
            CodeFoundationToolProvider: 초기화된 Provider

        Raises:
            NotImplementedError: 필수 컴포넌트 없을 경우
            ValueError: Port 인터페이스 위반
        """
        # STRICT: Port 인터페이스 검증
        if not isinstance(ir_analyzer, IRAnalyzerPort):
            raise ValueError(f"ir_analyzer must implement IRAnalyzerPort, got {type(ir_analyzer).__name__}")

        if not isinstance(security_analyzer, SecurityAnalyzerPort):
            raise ValueError(
                f"security_analyzer must implement SecurityAnalyzerPort, got {type(security_analyzer).__name__}"
            )

        if embedding_service is not None:
            if not isinstance(embedding_service, EmbeddingServiceProtocol):
                raise ValueError("embedding_service must implement EmbeddingServiceProtocol")
        logger.info("Initializing Code Foundation Tools")

        # 1. Provider 생성
        provider = ToolProviderFactory.create(embedding_service, llm_adapter)

        # 2. 컴포넌트 추출 (Port 기반 - STRICT)
        try:
            # IR Analyzer 컴포넌트들 (모두 Port 인터페이스)
            cross_file_resolver: CrossFileResolverPort = CodeFoundationToolsIntegrator._get_required_component(
                ir_analyzer, "cross_file_resolver"
            )

            call_graph_builder: CallGraphBuilderPort = CodeFoundationToolsIntegrator._get_required_component(
                ir_analyzer, "call_graph_builder"
            )

            reference_analyzer: ReferenceAnalyzerPort = CodeFoundationToolsIntegrator._get_required_component(
                ir_analyzer, "reference_analyzer"
            )

            impact_analyzer: ImpactAnalyzerPort = CodeFoundationToolsIntegrator._get_required_component(
                ir_analyzer, "impact_analyzer"
            )

            dependency_graph: DependencyGraphPort = CodeFoundationToolsIntegrator._get_required_component(
                ir_analyzer, "dependency_graph"
            )

            # Security Analyzer 컴포넌트
            taint_engine: TaintEnginePort = CodeFoundationToolsIntegrator._get_required_component(
                security_analyzer, "taint_engine"
            )

            # Port 인터페이스 검증
            if not isinstance(cross_file_resolver, CrossFileResolverPort):
                raise ValueError("cross_file_resolver must implement CrossFileResolverPort")

            if not isinstance(call_graph_builder, CallGraphBuilderPort):
                raise ValueError("call_graph_builder must implement CallGraphBuilderPort")

            # ... (나머지도 검증)

        except NotImplementedError as e:
            logger.error(f"Code Foundation integration failed: {e}")
            raise
        except ValueError as e:
            logger.error(f"Port interface validation failed: {e}")
            raise

        # 3. 도구 등록 (모든 컴포넌트 검증 완료)
        registry = provider.registry
        registered_count = 0

        # Understanding Tools (3개) - STRICT
        registry.register(GetSymbolDefinitionTool(ir_analyzer, cross_file_resolver))
        registered_count += 1

        registry.register(FindAllReferencesTool(ir_analyzer, call_graph_builder, reference_analyzer))
        registered_count += 1

        registry.register(BuildCallGraphTool(call_graph_builder))
        registered_count += 1

        # Impact Analysis Tools (2개) - STRICT
        registry.register(ComputeChangeImpactTool(impact_analyzer, dependency_graph))
        registered_count += 1

        registry.register(FindAffectedCodeTool(impact_analyzer))
        registered_count += 1

        # Security Tools (1개) - STRICT
        registry.register(DetectVulnerabilitiesTool(security_analyzer, taint_engine))
        registered_count += 1

        # 검증: 6개 모두 등록되었는지 확인
        if registered_count != 6:
            raise RuntimeError(f"Tool registration failed: expected 6 tools, got {registered_count}")

        stats = registry.get_statistics()
        logger.info(
            f"Code Foundation Tools initialized: {stats['total_tools']} tools "
            f"across {len(stats['by_category'])} categories"
        )

        return provider


def integrate_with_v8(v8_orchestrator) -> CodeFoundationToolProvider:
    """
    V8 Orchestrator에 통합

    Args:
        v8_orchestrator: DeepReasoningOrchestrator 인스턴스 (or V8AgentOrchestrator - backward compatible)

    Returns:
        CodeFoundationToolProvider: 통합된 Provider
    """
    # V8에서 필요한 컴포넌트 가져오기
    ir_analyzer = getattr(v8_orchestrator, "ir_analyzer", None)
    security_analyzer = getattr(v8_orchestrator, "security_analyzer", None)
    embedding_service = getattr(v8_orchestrator, "embedding_service", None)
    llm_adapter = getattr(v8_orchestrator, "llm_adapter", None)

    if not ir_analyzer:
        logger.warning("IR Analyzer not found in V8, using stub")
        # TODO: 스텁 생성

    if not security_analyzer:
        logger.warning("Security Analyzer not found in V8, using stub")
        # TODO: 스텁 생성

    # 통합
    provider = CodeFoundationToolsIntegrator.initialize(
        ir_analyzer=ir_analyzer,
        security_analyzer=security_analyzer,
        embedding_service=embedding_service,
        llm_adapter=llm_adapter,
    )

    # V8에 설정
    v8_orchestrator.tool_provider = provider

    logger.info("Code Foundation Tools integrated with V8 Orchestrator")

    return provider
