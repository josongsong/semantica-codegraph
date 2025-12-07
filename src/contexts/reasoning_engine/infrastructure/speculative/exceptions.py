"""
Speculative Execution Exceptions

Phase 2 교훈: 처음부터 명확한 exception hierarchy
"""


class SpeculativeError(Exception):
    """Base exception for speculative execution"""

    pass


class InvalidPatchError(SpeculativeError):
    """
    Patch가 invalid

    예:
    - AST syntax error
    - Type inconsistency
    - Dangling references
    """

    pass


class SimulationError(SpeculativeError):
    """
    Simulation 실행 중 에러

    예:
    - Delta application 실패
    - Graph consistency violation
    """

    pass


class RiskAnalysisError(SpeculativeError):
    """
    Risk analysis 중 에러

    예:
    - Missing graph data
    - Invalid impact calculation
    """

    pass
