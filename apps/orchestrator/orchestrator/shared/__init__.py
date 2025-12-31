"""
Agent Shared Resources

모든 agent contexts가 공유하는 자원:
- reasoning/: LATS, ToT, Reflection (범용 추론)
- ports/: 공통 인터페이스
- models/: 공통 도메인 모델

이 모듈은 agent contexts 간에만 공유됩니다.
contexts/code_foundation 등 다른 bounded contexts와는 독립적입니다.
"""

__all__ = []
