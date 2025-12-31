"""
Refactoring Adapters - SOTA급

Port 구현체:
- JediRopeRefactoringAdapter (Facade - RefactoringPort)
- JediSymbolFinder (SymbolFinderPort)
- ASTCodeTransformer (CodeTransformerPort)
- TypeHintGenerator (TypeHintGeneratorPort)

ISP/SRP 준수:
- 분리된 컴포넌트 직접 사용 가능
- Facade는 기존 호환성 유지
"""

# Facade (기존 호환성)
from .adapter import JediRopeRefactoringAdapter

# 분리된 컴포넌트 (ISP/SRP 준수)
from .code_transformer import ASTCodeTransformer
from .symbol_finder import JediSymbolFinder
from .type_hint_generator import TypeHintGenerator

__all__ = [
    # Facade (기존 호환성)
    "JediRopeRefactoringAdapter",
    # 분리된 컴포넌트 (ISP/SRP 준수)
    "JediSymbolFinder",
    "ASTCodeTransformer",
    "TypeHintGenerator",
]
