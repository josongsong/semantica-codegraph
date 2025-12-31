"""
Reasoning Engine Ports

추론 엔진의 포트(인터페이스) 정의
Hexagonal Architecture의 Port 레이어
"""

from .protocols import (
    # Data Types for Ports
    CacheEntry,
    # Protocols (Ports)
    CachePort,
    EffectAnalyzerPort,
    GraphAdapterPort,
    ImpactAnalyzerPort,
    ReasoningEnginePort,
    RiskAnalyzerPort,
    SimulatorPort,
    SliceResult,
    SlicerPort,
    # RFC-007 High-Performance Engine Ports
    TaintEnginePort,
    TaintPath,
    ValueFlowBuilderPort,
    VFGData,
    VFGExtractorPort,
)

__all__ = [
    # Protocols
    "ImpactAnalyzerPort",
    "EffectAnalyzerPort",
    "SlicerPort",
    "CachePort",
    "GraphAdapterPort",
    "SimulatorPort",
    "RiskAnalyzerPort",
    "ReasoningEnginePort",
    # RFC-007 High-Performance Engine Ports
    "TaintEnginePort",
    "VFGExtractorPort",
    "ValueFlowBuilderPort",
    # Data Types
    "SliceResult",
    "CacheEntry",
    "TaintPath",
    "VFGData",
]
