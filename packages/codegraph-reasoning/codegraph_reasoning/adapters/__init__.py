"""
Reasoning Engine Adapters

Infrastructure 컴포넌트를 Port로 래핑
Hexagonal Architecture의 Adapter 레이어
"""

from .cache_adapter import CacheAdapter
from .effect_adapter import EffectAnalyzerAdapter
from .impact_adapter import ImpactAnalyzerAdapter
from .risk_analyzer_adapter import RiskAnalyzerAdapter
from .simulator_adapter import SimulatorAdapter
from .slicer_adapter import SlicerAdapter

# RFC-007 High-Performance Engine Adapters
from .taint_engine_adapter import TaintEngineAdapter
from .value_flow_builder_adapter import ValueFlowBuilderAdapter
from .vfg_extractor_adapter import VFGExtractorAdapter

__all__ = [
    "ImpactAnalyzerAdapter",
    "EffectAnalyzerAdapter",
    "CacheAdapter",
    "SimulatorAdapter",
    "RiskAnalyzerAdapter",
    "SlicerAdapter",
    # RFC-007 High-Performance Engine Adapters
    "TaintEngineAdapter",
    "VFGExtractorAdapter",
    "ValueFlowBuilderAdapter",
]
