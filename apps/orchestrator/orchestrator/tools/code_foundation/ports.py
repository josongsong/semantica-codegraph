"""
Ports (Interfaces) for Hexagonal Architecture

Domain ← Port → Adapter
Code Foundation Tools는 이 Port만 의존, 실제 구현은 Adapter
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

# ============================================
# IR Analysis Port
# ============================================


@dataclass
class IRDocument:
    """IR 문서 추상화"""

    file_path: str
    language: str
    symbols: list[any]
    metadata: dict


@dataclass
class Symbol:
    """심볼 추상화"""

    name: str
    kind: str
    file_path: str
    line: int
    column: int
    signature: str | None = None
    documentation: str | None = None
    scope: str | None = None
    visibility: str | None = None


class IRAnalyzerPort(ABC):
    """
    IR 분석 Port

    Infrastructure 세부사항 숨김
    """

    @abstractmethod
    def analyze(self, file_path: str) -> IRDocument | None:
        """
        파일 분석 → IR 생성

        Args:
            file_path: 분석할 파일 경로

        Returns:
            IRDocument 또는 None (실패시)
        """
        pass


class CrossFileResolverPort(ABC):
    """크로스 파일 해결 Port"""

    @abstractmethod
    def resolve_symbol(self, symbol_name: str, source_doc: IRDocument, source_line: int | None = None) -> Symbol | None:
        """
        심볼 해결

        Args:
            symbol_name: 찾을 심볼
            source_doc: 소스 문서
            source_line: 소스 라인

        Returns:
            Symbol 또는 None
        """
        pass


# ============================================
# Call Graph Port
# ============================================


@dataclass
class CallGraphNode:
    """호출 그래프 노드"""

    name: str
    file_path: str
    line: int


@dataclass
class CallGraphEdge:
    """호출 그래프 엣지"""

    caller: str
    callee: str
    confidence: float


class CallGraph:
    """호출 그래프"""

    def __init__(self):
        self.nodes: list[CallGraphNode] = []
        self.edges: list[CallGraphEdge] = []

    def get_callers(self, function_name: str, depth: int = 1) -> list[str]:
        """호출자 목록"""
        return []

    def get_callees(self, function_name: str, depth: int = 1) -> list[str]:
        """피호출자 목록"""
        return []


class CallGraphBuilderPort(ABC):
    """호출 그래프 빌더 Port"""

    @abstractmethod
    def build_precise_cg(self, target_function: str, file_path: str, use_type_narrowing: bool = False) -> CallGraph:
        """
        정밀 호출 그래프 구축

        Args:
            target_function: 대상 함수
            file_path: 파일 경로
            use_type_narrowing: 타입 좁히기 사용

        Returns:
            CallGraph
        """
        pass


# ============================================
# Reference Analysis Port
# ============================================


@dataclass
class Reference:
    """참조"""

    file_path: str
    line: int
    column: int
    context_code: str
    ref_type: str  # call, assignment, etc.


class ReferenceAnalyzerPort(ABC):
    """참조 분석 Port"""

    @abstractmethod
    def find_references(self, symbol_name: str, definition_file: str, max_results: int = 100) -> list[Reference]:
        """
        참조 찾기

        Args:
            symbol_name: 심볼 이름
            definition_file: 정의 파일
            max_results: 최대 결과 수

        Returns:
            참조 목록
        """
        pass


# ============================================
# Impact Analysis Port
# ============================================


@dataclass
class ImpactResult:
    """영향 분석 결과"""

    affected_files: list[str]
    affected_functions: list[str]
    risk_score: float
    summary: str
    breaking_changes: list[str]


class ImpactAnalyzerPort(ABC):
    """영향 분석 Port"""

    @abstractmethod
    def analyze_impact(self, file_path: str, function_name: str | None, change_type: str) -> ImpactResult:
        """
        영향 분석

        Args:
            file_path: 대상 파일
            function_name: 대상 함수
            change_type: 변경 유형

        Returns:
            ImpactResult
        """
        pass

    @abstractmethod
    def find_affected(self, file_path: str, symbol_name: str | None) -> list[str]:
        """영향받는 위치 찾기"""
        pass


# ============================================
# Dependency Graph Port
# ============================================


class DependencyGraphPort(ABC):
    """의존성 그래프 Port"""

    @abstractmethod
    def get_dependencies(self, file_path: str) -> list[str]:
        """파일 의존성 가져오기"""
        pass


# ============================================
# Security Analysis Port
# ============================================


@dataclass
class SecurityIssue:
    """보안 이슈"""

    issue_type: str
    severity: str
    file: str
    line: int
    column: int
    message: str
    confidence: float
    taint_path: list[str] | None = None


class TaintEnginePort(ABC):
    """Taint 엔진 Port"""

    @abstractmethod
    def trace_taint(self, source: str, sink: str) -> list[str] | None:
        """Taint 추적"""
        pass


class SecurityAnalyzerPort(ABC):
    """보안 분석 Port"""

    @abstractmethod
    def analyze(self, file_path: str, mode: str = "quick") -> list[SecurityIssue]:
        """
        보안 분석

        Args:
            file_path: 분석할 파일
            mode: 스캔 모드

        Returns:
            보안 이슈 목록
        """
        pass


# ============================================
# Embedding Service Protocol
# ============================================


@runtime_checkable
class EmbeddingServiceProtocol(Protocol):
    """
    임베딩 서비스 Protocol

    Duck Typing으로 구현 강제하지 않음
    """

    def embed(self, text: str) -> np.ndarray:
        """
        텍스트 → 임베딩 벡터

        Args:
            text: 임베딩할 텍스트

        Returns:
            numpy array (벡터)
        """
        ...


# ============================================
# LLM Adapter Protocol
# ============================================


@runtime_checkable
class LLMAdapterProtocol(Protocol):
    """LLM 어댑터 Protocol"""

    provider: str  # "openai", "anthropic", etc.

    def chat(self, messages: list[dict], **kwargs) -> dict:
        """
        LLM 채팅

        Args:
            messages: 메시지 목록
            **kwargs: 추가 파라미터

        Returns:
            응답 딕셔너리
        """
        ...
