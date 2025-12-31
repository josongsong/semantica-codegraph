"""
Real Adapters for Code Foundation (Production-Grade)

v2: Domain 컴포넌트 연동 완료 (2024-12-13)
"""

from .real_adapters import (
    RealCallGraphBuilderAdapter,
    RealCrossFileResolverAdapter,
    RealDependencyGraphAdapter,
    RealImpactAnalyzerAdapter,
    RealIRAnalyzerAdapter,
    RealReferenceAnalyzerAdapter,
    RealSecurityAnalyzerAdapter,
    RealTaintEngineAdapter,
)

# Backward compatibility aliases
StubIRAnalyzerAdapter = RealIRAnalyzerAdapter
StubSecurityAnalyzerAdapter = RealSecurityAnalyzerAdapter

__all__ = [
    # Real adapters
    "RealIRAnalyzerAdapter",
    "RealSecurityAnalyzerAdapter",
    "RealCrossFileResolverAdapter",
    "RealCallGraphBuilderAdapter",
    "RealReferenceAnalyzerAdapter",
    "RealImpactAnalyzerAdapter",
    "RealDependencyGraphAdapter",
    "RealTaintEngineAdapter",
    # Backward compatibility
    "StubIRAnalyzerAdapter",
    "StubSecurityAnalyzerAdapter",
]
