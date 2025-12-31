"""
RFC Application Layer (RFC-027)

Executors orchestrate Spec → Adapter → Analyzer flow.

Architecture:
- Application Layer (Hexagonal)
- Depends on: Domain (Specs, Envelope)
- Depends on: Adapters (TaintAdapter, SCCPAdapter, etc.)
- Depends on: code_foundation (Analyzers)

Executors:
- ExecuteExecutor: Execute any spec
- ValidateExecutor: Validate spec before execution
- PlanExecutor: Generate execution plan
- ExplainExecutor: Explain results

RFC-027 Section 13: Implementation Phases
"""

from .execute_executor import ExecuteExecutor

__all__ = [
    "ExecuteExecutor",
]
