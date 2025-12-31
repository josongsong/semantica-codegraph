"""
Analyzer Framework Domain

RFC-024 Part 2: Analyzer Framework - Domain Layer

Hexagonal Architecture:
- Domain Layer: 추상화 (Ports, 의존성 명세)
- Infrastructure Layer: 구현 (Registry, Pipeline)
"""

from .context import AnalysisContext
from .dependency import DependencySpec, IRFieldDependency, OptionalDependency, RequiredDependency
from .ports import AnalyzerCategory, AnalyzerTier, IAnalyzer

__all__ = [
    "IAnalyzer",
    "AnalyzerCategory",
    "AnalyzerTier",
    "DependencySpec",
    "RequiredDependency",
    "OptionalDependency",
    "IRFieldDependency",
    "AnalysisContext",
]
