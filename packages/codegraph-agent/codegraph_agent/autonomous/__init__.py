"""
Autonomous Mode (RFC-060)

SWE-Bench 스타일 자율 코딩:
- TDD Cycle (Reproduction-First)
- SBFL Localization
- Impact Test Selection
- Patch Minimization

사용 시나리오:
- 복잡한 버그 수정
- 대규모 리팩토링
- 장기 실행 (분~시간)
"""

from codegraph_agent.autonomous.cascade_orchestrator import CascadeOrchestrator
from codegraph_agent.autonomous.sbfl_analyzer import SBFLAnalyzer, SuspiciousLine

__all__ = [
    "CascadeOrchestrator",
    "SBFLAnalyzer",
    "SuspiciousLine",
]
