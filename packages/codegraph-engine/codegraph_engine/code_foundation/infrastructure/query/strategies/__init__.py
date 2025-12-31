"""
Query Execution Strategies - Infrastructure Implementations

Concrete implementations of QueryExecutionStrategy Port.

Strategies:
- DefaultExecutionStrategy: Current implementation (depth-first-like)
- CostBasedExecutionStrategy: Choose operations based on estimated cost
"""

from .default_strategy import DefaultExecutionStrategy

__all__ = ["DefaultExecutionStrategy"]
