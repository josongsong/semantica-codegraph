"""
Resilience Patterns for Multi-Index Infrastructure

외부 서비스 장애 대응을 위한 복원력 패턴:

- CircuitBreaker: 장애 서비스 빠른 실패
- CircuitBreakerRegistry: 서비스별 Circuit Breaker 관리

Usage:
    from codegraph_engine.multi_index.infrastructure.resilience import (
        CircuitBreaker,
        CircuitBreakerConfig,
        CircuitBreakerRegistry,
        get_circuit_breaker_registry,
    )

    # 방법 1: 직접 생성
    breaker = CircuitBreaker("qdrant")
    result = await breaker.call(lambda: client.search(...))

    # 방법 2: 글로벌 레지스트리
    registry = get_circuit_breaker_registry()
    breaker = await registry.get_or_create("postgres")
"""

from codegraph_engine.multi_index.infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitStats,
    get_circuit_breaker_registry,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitBreakerRegistry",
    "CircuitState",
    "CircuitStats",
    "get_circuit_breaker_registry",
]
