"""
Shared Kernel - Bounded Context 간 공유 모델

Governance Rules (RFC-021):
1. Pure Data & Contracts Only: @dataclass, Enum, Protocol만 허용
2. No Implementation: Builder, Slicer 등 실제 구현 금지
3. Strict Dependency: Python stdlib(typing, dataclasses, enum)만 의존

Purpose:
- code_foundation ↔ reasoning_engine 순환 의존성 해결
- PDG, Slice 관련 공통 모델 정의
- 공통 ENUM 정의 (AnalysisMode)
"""

from codegraph_shared.kernel.contracts.modes import AnalysisMode

__all__ = ["AnalysisMode"]
