"""
Code Editing Ports (Hexagonal Architecture) - SOTA급

순수 인터페이스 - 구현체 없음 (Protocol 사용)
Domain과 Adapter 사이의 경계 정의

ISP (Interface Segregation Principle) 준수:
- FIMPort: 코드 완성만
- SymbolFinderPort: 심볼 찾기만
- CodeTransformerPort: 코드 변환만 (rename, extract)
- TypeHintGeneratorPort: 타입 힌트 생성만
- RefactoringPort: 위 3개를 합친 Facade (기존 호환성)
- AtomicEditPort: Atomic 편집만

책임:
- FIM Port
- Refactoring Port (분리됨)
- Atomic Edit Port
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from apps.orchestrator.orchestrator.domain.code_editing import (
    AtomicEditRequest,
    AtomicEditResult,
    Completion,
    ExtractMethodRequest,
    FIMRequest,
    FIMResult,
    RefactoringResult,
    RenameRequest,
    SymbolInfo,
)

# ============================================================================
# FIM Port
# ============================================================================


@runtime_checkable
class FIMPort(Protocol):
    """
    Fill-in-the-Middle Port

    책임:
    - LLM을 통한 코드 완성
    - 스트리밍 지원
    - 다중 후보 생성

    구현체:
    - LiteLLMFIMAdapter (src/agent/adapters/code_editing/fim/)
    """

    async def complete(self, request: FIMRequest) -> FIMResult:
        """
        코드 완성 (일반 모드)

        Args:
            request: FIM 요청

        Returns:
            FIMResult: 완성 결과 (다중 후보 포함)

        Raises:
            ValueError: Invalid request
            TimeoutError: LLM timeout
            RuntimeError: LLM API error
        """
        ...

    async def complete_streaming(
        self,
        request: FIMRequest,
    ) -> AsyncIterator[Completion]:
        """
        코드 완성 (스트리밍 모드)

        Args:
            request: FIM 요청

        Yields:
            Completion: 완성 후보 (실시간 스트리밍)

        Raises:
            ValueError: Invalid request
            TimeoutError: LLM timeout
            RuntimeError: LLM API error
        """
        ...


# ============================================================================
# Refactoring Ports (ISP 준수 - 분리됨)
# ============================================================================


@runtime_checkable
class SymbolFinderPort(Protocol):
    """
    Symbol Finder Port (ISP 분리)

    책임:
    - Symbol 찾기 (Jedi 기반)
    - Symbol 정보 조회

    구현체:
    - JediSymbolFinder (src/agent/adapters/code_editing/refactoring/)
    """

    async def find_symbol(self, file_path: str, symbol_name: str) -> SymbolInfo | None:
        """
        Symbol 찾기 (Jedi 기반)

        Args:
            file_path: 파일 경로
            symbol_name: Symbol 이름

        Returns:
            SymbolInfo | None: Symbol 정보 (없으면 None)

        Raises:
            FileNotFoundError: File not found
            RuntimeError: Analysis failed
        """
        ...


@runtime_checkable
class CodeTransformerPort(Protocol):
    """
    Code Transformer Port (ISP 분리)

    책임:
    - Symbol rename
    - Method/Function 추출

    구현체:
    - ASTCodeTransformer (src/agent/adapters/code_editing/refactoring/)
    """

    async def rename_symbol(self, request: RenameRequest) -> RefactoringResult:
        """
        Symbol 이름 변경

        Args:
            request: Rename 요청

        Returns:
            RefactoringResult: 리팩토링 결과

        Raises:
            ValueError: Invalid request
            FileNotFoundError: File not found
            RuntimeError: Refactoring failed
        """
        ...

    async def extract_method(self, request: ExtractMethodRequest) -> RefactoringResult:
        """
        메서드/함수 추출

        Args:
            request: Extract 요청

        Returns:
            RefactoringResult: 리팩토링 결과

        Raises:
            ValueError: Invalid request
            FileNotFoundError: File not found
            RuntimeError: Refactoring failed
        """
        ...


@runtime_checkable
class TypeHintGeneratorPort(Protocol):
    """
    Type Hint Generator Port (ISP 분리)

    책임:
    - 타입 힌트 자동 생성 (Python only)

    구현체:
    - TypeHintGenerator (src/agent/adapters/code_editing/refactoring/)
    """

    async def generate_type_hints(self, file_path: str) -> RefactoringResult:
        """
        타입 힌트 자동 생성 (Python only)

        Args:
            file_path: 파일 경로

        Returns:
            RefactoringResult: 타입 힌트 추가 결과

        Raises:
            FileNotFoundError: File not found
            RuntimeError: Type inference failed
        """
        ...


@runtime_checkable
class RefactoringPort(SymbolFinderPort, CodeTransformerPort, TypeHintGeneratorPort, Protocol):
    """
    Refactoring Port (Facade - 기존 호환성)

    ISP 위반을 해결하면서 기존 코드 호환성 유지
    SymbolFinderPort + CodeTransformerPort + TypeHintGeneratorPort

    구현체:
    - JediRopeRefactoringAdapter (src/agent/adapters/code_editing/refactoring/)

    Note:
    - 새 코드에서는 분리된 Port 사용 권장
    - 기존 코드는 이 Facade 사용 가능
    """

    pass


# ============================================================================
# Atomic Edit Port
# ============================================================================


@runtime_checkable
class AtomicEditPort(Protocol):
    """
    Atomic Edit Port

    책임:
    - Multi-file atomic transaction
    - Hash-based conflict detection
    - Rollback 지원
    - Multi-agent concurrency

    구현체:
    - AtomicEditAdapter (src/agent/adapters/code_editing/atomic_edit/)
    """

    async def execute(self, request: AtomicEditRequest) -> AtomicEditResult:
        """
        Atomic edit 실행

        Args:
            request: Atomic edit 요청

        Returns:
            AtomicEditResult: 실행 결과

        Raises:
            ValueError: Invalid request
            TimeoutError: Lock timeout
            RuntimeError: Transaction failed
        """
        ...

    async def rollback(self, rollback_id: str) -> AtomicEditResult:
        """
        Rollback 실행

        Args:
            rollback_id: Rollback ID

        Returns:
            AtomicEditResult: Rollback 결과

        Raises:
            ValueError: Invalid rollback_id
            RuntimeError: Rollback failed
        """
        ...

    async def check_conflicts(self, request: AtomicEditRequest) -> list[str]:
        """
        충돌 사전 체크 (dry-run)

        Args:
            request: Atomic edit 요청

        Returns:
            list[str]: 충돌 파일 목록 (빈 리스트면 충돌 없음)

        Raises:
            ValueError: Invalid request
        """
        ...


# ============================================================================
# Export (기존 호환성)
# ============================================================================

__all__ = [
    # FIM
    "FIMPort",
    # Refactoring (분리됨 - ISP)
    "SymbolFinderPort",
    "CodeTransformerPort",
    "TypeHintGeneratorPort",
    "RefactoringPort",  # Facade (기존 호환성)
    # Atomic Edit
    "AtomicEditPort",
]
