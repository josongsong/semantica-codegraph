"""
Rename Strategy Protocol (Hexagonal Architecture)

DIP 준수: Adapter에서 Strategy Protocol 분리

책임:
- Symbol rename 추상화
- Strategy Pattern 지원

SOLID:
- S: Rename 전략만 정의
- O: 새 Rename 전략 추가 용이 (Rope, LSP 등)
- L: Protocol 완벽히 구현 가능
- I: rename 메서드만 정의
- D: 구체 구현에 의존하지 않음
"""

from typing import Protocol, runtime_checkable

from apps.orchestrator.orchestrator.domain.code_editing import RenameRequest

# ============================================================================
# Rename Strategy Protocol
# ============================================================================


@runtime_checkable
class RenameStrategyProtocol(Protocol):
    """
    Rename Strategy Protocol

    Symbol rename 전략 인터페이스

    구현체:
    - ASTRenameStrategy: AST + regex 기반 (기본)
    - RopeRenameStrategy: Rope 기반 (고급)
    - 향후: LSPRenameStrategy (Language Server Protocol)
    """

    async def rename(
        self,
        request: RenameRequest,
        content: str,
    ) -> tuple[str, list[str]]:
        """
        Symbol 이름 변경

        Args:
            request: Rename 요청
            content: 파일 내용

        Returns:
            tuple[str, list[str]]: (새 내용, 경고 메시지)

        Raises:
            ValueError: Invalid request
            RuntimeError: Rename failed
        """
        ...


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "RenameStrategyProtocol",
]
