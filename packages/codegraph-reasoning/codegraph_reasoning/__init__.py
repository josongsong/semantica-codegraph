"""
Reasoning Engine Context

Semantica v6의 추론 엔진 (Reasoning Engine) 구현.
검색(Search)을 넘어 코드 시뮬레이션과 추론(Reasoning)을 제공합니다.

주요 기능:
- Impact-Based Partial Rebuild (Symbol-level hash)
- Speculative Graph Execution (CoW + Overlay)
- Semantic Change Detection (Effect System)
- Program Slice Engine (PDG-based RAG optimization)
"""

__version__ = "6.0.0-alpha"

# Application layer (main entry points)
# Adapters (port implementations)
from .adapters import (
    CacheAdapter,
    EffectAnalyzerAdapter,
    ImpactAnalyzerAdapter,
    RiskAnalyzerAdapter,
    SimulatorAdapter,
    SlicerAdapter,
)
from .application.incremental_builder import ImpactAnalysisPlanner
from .application.reasoning_pipeline import ReasoningContext, ReasoningPipeline, ReasoningResult

# Domain models
from .domain import (
    Delta,
    DeltaOperation,
    EffectDiff,
    EffectSet,
    EffectSeverity,
    # Effect models
    EffectType,
    # Legacy hash-based models (for incremental rebuild)
    HashBasedImpactLevel,
    # Impact models (for impact analysis: NONE/LOW/MEDIUM/HIGH/CRITICAL)
    ImpactLevel,
    ImpactNode,
    ImpactPath,
    ImpactReport,
    PatchType,
    PropagationType,
    RiskLevel,
    RiskReport,
    # Speculative models
    SpeculativePatch,
)

# Ports (protocols)
from .ports import (
    CachePort,
    EffectAnalyzerPort,
    ImpactAnalyzerPort,
    ReasoningEnginePort,
    RiskAnalyzerPort,
    SimulatorPort,
    SlicerPort,
)

__all__ = [
    # Version
    "__version__",
    # Application
    "ReasoningPipeline",
    "ReasoningContext",
    "ReasoningResult",
    "ImpactAnalysisPlanner",
    # Adapters
    "ImpactAnalyzerAdapter",
    "EffectAnalyzerAdapter",
    "SimulatorAdapter",
    "RiskAnalyzerAdapter",
    "SlicerAdapter",
    "CacheAdapter",
    # Domain - Effect
    "EffectType",
    "EffectDiff",
    "EffectSet",
    "EffectSeverity",
    # Domain - Impact
    "ImpactLevel",
    "ImpactNode",
    "ImpactPath",
    "ImpactReport",
    "PropagationType",
    # Domain - Speculative
    "SpeculativePatch",
    "RiskLevel",
    "RiskReport",
    "Delta",
    "DeltaOperation",
    "PatchType",
    # Domain - Legacy (hash-based rebuild)
    "HashBasedImpactLevel",
    # Ports
    "ImpactAnalyzerPort",
    "EffectAnalyzerPort",
    "SlicerPort",
    "CachePort",
    "SimulatorPort",
    "RiskAnalyzerPort",
    "ReasoningEnginePort",
]
