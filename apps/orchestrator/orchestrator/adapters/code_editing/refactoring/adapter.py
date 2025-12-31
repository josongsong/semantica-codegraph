"""
Jedi/Rope Refactoring Adapter (Facade) - SOTA급

Port: RefactoringPort
Technology: Jedi (분석) + AST (리팩토링)

책임:
- RefactoringPort 구현 (Facade 패턴)
- 분리된 컴포넌트 조합

SOLID:
- S: Facade만 담당 - 실제 로직은 분리된 클래스에서
- O: 새 기능 추가 시 컴포넌트 추가만 필요
- L: RefactoringPort 완벽히 구현
- I: 분리된 Port들도 개별 사용 가능
- D: Protocol 기반 의존성

아키텍처:
                    ┌─────────────────────────────────┐
                    │   JediRopeRefactoringAdapter    │
                    │         (Facade)                │
                    └─────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │JediSymbol   │    │ASTCode      │    │TypeHint     │
    │Finder       │    │Transformer  │    │Generator    │
    └─────────────┘    └─────────────┘    └─────────────┘
           │                   │                   │
           ▼                   ▼                   ▼
    SymbolFinderPort   CodeTransformerPort   TypeHintGeneratorPort
"""

import logging
from pathlib import Path

from apps.orchestrator.orchestrator.domain.code_editing import (
    ExtractMethodRequest,
    RefactoringResult,
    RenameRequest,
    SymbolInfo,
)

from .code_transformer import ASTCodeTransformer
from .symbol_finder import JediSymbolFinder
from .type_hint_generator import TypeHintGenerator

logger = logging.getLogger(__name__)


class JediRopeRefactoringAdapter:
    """
    Jedi/Rope 기반 Refactoring Adapter (Facade)

    RefactoringPort 구현체

    SRP를 준수하여 실제 로직은 분리된 클래스에서 처리:
    - JediSymbolFinder: Symbol 찾기
    - ASTCodeTransformer: 코드 변환 (rename, extract)
    - TypeHintGenerator: 타입 힌트 생성

    Usage:
        # Facade 사용 (기존 호환성)
        adapter = JediRopeRefactoringAdapter("/workspace")
        symbol = await adapter.find_symbol("main.py", "my_func")
        result = await adapter.rename_symbol(request)

        # 분리된 컴포넌트 직접 사용 (ISP 준수)
        finder = JediSymbolFinder("/workspace")
        symbol = await finder.find_symbol("main.py", "my_func")
    """

    def __init__(self, workspace_root: str, use_rope: bool = False, use_jedi: bool = True):
        """
        Args:
            workspace_root: Workspace 루트 경로
            use_rope: Rope 사용 여부 (고급 rename)
            use_jedi: Jedi 사용 여부 (타입 추론)
        """
        self.workspace_root = Path(workspace_root)

        # 분리된 컴포넌트 초기화
        self._symbol_finder = JediSymbolFinder(workspace_root)
        self._code_transformer = ASTCodeTransformer(workspace_root, use_rope=use_rope)
        self._type_hint_generator = TypeHintGenerator(workspace_root, use_jedi=use_jedi)

        logger.info(
            f"JediRopeRefactoringAdapter initialized: workspace={workspace_root}, rope={use_rope}, jedi={use_jedi}"
        )

    # ========================================================================
    # SymbolFinderPort
    # ========================================================================

    async def find_symbol(self, file_path: str, symbol_name: str) -> SymbolInfo | None:
        """
        Symbol 찾기 (Jedi 기반)

        위임: JediSymbolFinder.find_symbol
        """
        return await self._symbol_finder.find_symbol(file_path, symbol_name)

    # ========================================================================
    # CodeTransformerPort
    # ========================================================================

    async def rename_symbol(self, request: RenameRequest) -> RefactoringResult:
        """
        Symbol 이름 변경

        위임: ASTCodeTransformer.rename_symbol
        """
        return await self._code_transformer.rename_symbol(request)

    async def extract_method(self, request: ExtractMethodRequest) -> RefactoringResult:
        """
        메서드/함수 추출

        위임: ASTCodeTransformer.extract_method
        """
        return await self._code_transformer.extract_method(request)

    # ========================================================================
    # TypeHintGeneratorPort
    # ========================================================================

    async def generate_type_hints(self, file_path: str) -> RefactoringResult:
        """
        타입 힌트 자동 생성

        위임: TypeHintGenerator.generate_type_hints
        """
        return await self._type_hint_generator.generate_type_hints(file_path)

    # ========================================================================
    # Component Access (테스트/확장용)
    # ========================================================================

    @property
    def symbol_finder(self) -> JediSymbolFinder:
        """SymbolFinder 컴포넌트 접근"""
        return self._symbol_finder

    @property
    def code_transformer(self) -> ASTCodeTransformer:
        """CodeTransformer 컴포넌트 접근"""
        return self._code_transformer

    @property
    def type_hint_generator(self) -> TypeHintGenerator:
        """TypeHintGenerator 컴포넌트 접근"""
        return self._type_hint_generator
