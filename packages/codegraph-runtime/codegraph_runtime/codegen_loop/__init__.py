"""
CodeGen Loop Context

Hexagonal Architecture:
- domain: 순수 비즈니스 로직 (외부 의존 없음)
- application: Use Cases + Ports (인터페이스)
- infrastructure: Adapters (LLM, HCG, Sandbox)
"""

from .api import CodeGenLoopAPI

__all__ = ["CodeGenLoopAPI"]
