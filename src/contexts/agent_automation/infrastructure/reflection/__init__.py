"""
Reflection Layer - Self-Critique and Improvement System

Agent가 자신의 결과를 평가하고 개선하는 Reflection Loop 구현.

Components:
- ReflectionEngine: 결과 평가 및 개선 제안
- ImprovementLoop: Reflection 기반 재시도 루프
- CriteriaEvaluator: 다양한 평가 기준 적용

Usage:
    from src.contexts.agent_automation.infrastructure.reflection import ReflectionEngine

    engine = ReflectionEngine(llm_client=llm)
    reflection = await engine.reflect(result, task, context)

    if reflection.needs_improvement:
        improved = await engine.improve(result, reflection)
"""

from src.contexts.agent_automation.infrastructure.reflection.engine import ReflectionEngine
from src.contexts.agent_automation.infrastructure.reflection.evaluator import CriteriaEvaluator
from src.contexts.agent_automation.infrastructure.reflection.loop import ImprovementLoop

__all__ = [
    "ReflectionEngine",
    "CriteriaEvaluator",
    "ImprovementLoop",
]
