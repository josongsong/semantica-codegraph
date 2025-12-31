"""
Code Foundation Adapters

외부 Foundation 모듈과의 연결을 담당하는 어댑터
Hexagonal Architecture의 Adapter 레이어
"""

from .foundation_adapters import (
    FoundationChunkerAdapter,
    FoundationGraphBuilderAdapter,
    FoundationIRGeneratorAdapter,
    FoundationParserAdapter,
)

__all__ = [
    "FoundationParserAdapter",
    "FoundationIRGeneratorAdapter",
    "FoundationGraphBuilderAdapter",
    "FoundationChunkerAdapter",
]
