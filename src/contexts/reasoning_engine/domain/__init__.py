"""
Domain Layer - Reasoning Engine

비즈니스 로직과 도메인 모델 정의.
외부 인프라에 의존하지 않는 순수한 도메인 객체들.
"""

from .models import (
    ChangeType,
    # Speculative Execution
    DeltaLayer,
    EffectDiff,
    EffectSet,
    # Effect System
    EffectType,
    ErrorSnapshot,
    ImpactLevel,
    ImpactType,
    PatchMetadata,
    RelevanceScore,
    # Semantic Diff
    SemanticDiff,
    SliceNode,
    # Program Slice
    SliceResult,
    # Impact Analysis
    SymbolHash,
)
from .ports import (
    EffectAnalyzerPort,
    ImpactAnalyzerPort,
    ReasoningEnginePort,
    SemanticDifferPort,
    SlicerPort,
    SpeculativeExecutorPort,
)

__all__ = [
    # Models
    "SymbolHash",
    "ImpactLevel",
    "ImpactType",
    "EffectType",
    "EffectSet",
    "EffectDiff",
    "SemanticDiff",
    "ChangeType",
    "DeltaLayer",
    "PatchMetadata",
    "ErrorSnapshot",
    "SliceResult",
    "SliceNode",
    "RelevanceScore",
    # Ports
    "ReasoningEnginePort",
    "ImpactAnalyzerPort",
    "EffectAnalyzerPort",
    "SemanticDifferPort",
    "SpeculativeExecutorPort",
    "SlicerPort",
]
