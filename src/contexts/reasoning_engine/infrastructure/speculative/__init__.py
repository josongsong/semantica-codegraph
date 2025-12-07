"""
Speculative Graph Execution Infrastructure

LLM 패치를 실제로 적용하기 전에 시뮬레이션하고 위험도를 분석합니다.

Core Components:
- DeltaGraph: Copy-on-Write graph overlay
- GraphSimulator: Patch simulation engine
- RiskAnalyzer: Breaking change detection & risk scoring
- OverlayManager: Multi-patch stack management
"""

from .exceptions import (
    InvalidPatchError,
    RiskAnalysisError,
    SimulationError,
    SpeculativeError,
)

__all__ = [
    "SpeculativeError",
    "InvalidPatchError",
    "SimulationError",
    "RiskAnalysisError",
]
