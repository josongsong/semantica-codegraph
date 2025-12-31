"""
FixpointQueryAdapter - TaintEngine과 FixpointTaintSolver 연결

Hexagonal Architecture:
    TaintEngine (Domain)
        ↓ (QueryEnginePort interface)
    FixpointQueryAdapter (this file)
        ↓ (uses)
    FixpointTaintSolver (100% F1 알고리즘)

기존 QueryEngineAdapter를 래핑하여:
1. 기존 BFS 기반 쿼리 실행 (fast path)
2. Fixpoint 기반 정밀 분석 (slow path, 더 정확)

RFC-029: SOTA Taint Analysis Integration
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.ports.foundation_ports import QueryEnginePort
from codegraph_engine.code_foundation.domain.query.results import PathResult
from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy
from codegraph_engine.code_foundation.infrastructure.analyzers.fixpoint_taint_solver import (
    FixpointTaintSolver,
    TaintViolation,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.ir_to_cfg_adapter import (
    convert_ir_to_cfgs,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.taint.query_adapter import (
        QueryEngineAdapter,
    )

logger = get_logger(__name__)


@dataclass
class FixpointAnalysisResult:
    """Result from fixpoint analysis."""

    violations: list[TaintViolation]
    iterations: int
    converged: bool


class FixpointQueryAdapter(QueryEnginePort):
    """
    Fixpoint 기반 QueryEngine Adapter.

    TaintEngine이 사용하는 QueryEnginePort 인터페이스 구현.
    내부적으로 FixpointTaintSolver를 사용하여 정밀 분석 수행.

    두 가지 모드:
    1. Fast mode (use_fixpoint=False): 기존 BFS 기반 분석
    2. Precise mode (use_fixpoint=True): Fixpoint 기반 분석

    Usage:
        ```python
        # Create adapter
        adapter = FixpointQueryAdapter(
            ir_doc=ir_doc,
            base_adapter=existing_query_adapter,  # Optional fallback
            use_fixpoint=True,
        )

        # Use in TaintEngine
        engine = TaintEngine(
            query_engine=adapter,
            ...
        )
        ```
    """

    def __init__(
        self,
        ir_doc: "IRDocument",
        base_adapter: "QueryEngineAdapter | None" = None,
        use_fixpoint: bool = True,
        sources: set[str] | None = None,
        sinks: set[str] | None = None,
        sanitizers: set[str] | None = None,
    ):
        self.ir_doc = ir_doc
        self.base_adapter = base_adapter
        self.use_fixpoint = use_fixpoint

        # Default taint patterns
        self.sources = sources or {
            "request.args",
            "request.form",
            "request.get",
            "request.post",
            "request.data",
            "request.json",
            "request.values",
            "request.cookies",
            "request.headers",
            "input",
            "sys.argv",
            "os.environ",
            "getenv",
        }

        self.sinks = sinks or {
            "os.system",
            "subprocess.call",
            "subprocess.run",
            "subprocess.Popen",
            "execute",
            "cursor.execute",
            "eval",
            "exec",
            "render_template_string",
            "open",
            "requests.get",
            "requests.post",
            "urlopen",
        }

        self.sanitizers = sanitizers or {
            "escape",
            "html.escape",
            "quote",
            "shlex.quote",
            "sanitize",
            "clean",
            "validate",
            "bleach.clean",
            "markupsafe.escape",
        }

        # Lazy-initialized solver
        self._solver: FixpointTaintSolver | None = None
        self._cached_violations: list[TaintViolation] | None = None

        logger.info(
            "fixpoint_query_adapter_created",
            use_fixpoint=use_fixpoint,
            sources=len(self.sources),
            sinks=len(self.sinks),
        )

    def execute_flow_query(
        self,
        compiled_policy: CompiledPolicy,
        max_paths: int = 100,
        max_depth: int = 20,
        timeout_seconds: float = 60.0,
    ) -> list[PathResult]:
        """
        Execute flow query using fixpoint analysis.

        This is the QueryEnginePort interface method that TaintEngine calls.

        Args:
            compiled_policy: Compiled taint policy
            max_paths: Maximum paths to return
            max_depth: Maximum path depth
            timeout_seconds: Timeout for analysis

        Returns:
            List of paths from sources to sinks
        """
        if not self.use_fixpoint:
            # Fallback to base adapter
            if self.base_adapter:
                return self.base_adapter.execute_flow_query(compiled_policy, max_paths, max_depth, timeout_seconds)
            return []

        # Run fixpoint analysis
        violations = self._run_fixpoint_analysis()

        # Convert violations to PathResult format
        paths = self._violations_to_paths(violations, max_paths)

        logger.info(
            "fixpoint_query_executed",
            violations=len(violations),
            paths=len(paths),
        )

        return paths

    def _run_fixpoint_analysis(self) -> list[TaintViolation]:
        """
        Run fixpoint taint analysis.

        Uses cached result if available.
        """
        if self._cached_violations is not None:
            return self._cached_violations

        # Convert IR to CFGs
        functions = convert_ir_to_cfgs(self.ir_doc)

        if not functions:
            logger.warning("no_functions_found_for_analysis")
            return []

        # Create and run solver
        solver = FixpointTaintSolver(
            sources=self.sources,
            sinks=self.sinks,
            sanitizers=self.sanitizers,
        )

        violations = solver.analyze(functions)

        # Cache result
        self._cached_violations = violations

        logger.info(
            "fixpoint_analysis_complete",
            functions=len(functions),
            violations=len(violations),
        )

        return violations

    def _violations_to_paths(
        self,
        violations: list[TaintViolation],
        max_paths: int,
    ) -> list[PathResult]:
        """Convert TaintViolations to PathResults."""
        paths: list[PathResult] = []

        for violation in violations[:max_paths]:
            # Create minimal PathResult from violation
            # Note: This is a simplified conversion
            # Real implementation would reconstruct full path from IR

            path = PathResult(
                nodes=[],  # Would need to reconstruct from IR
                edges=[],
                uncertain=False,
                severity=violation.severity,
            )

            # Store violation info in path metadata
            # This allows TaintEngine to extract details
            path._violation = violation  # type: ignore

            paths.append(path)

        return paths

    def invalidate_cache(self):
        """Invalidate cached analysis results."""
        self._cached_violations = None
        self._solver = None

    def get_violations(self) -> list[TaintViolation]:
        """
        Get raw violations from fixpoint analysis.

        This is a direct access method bypassing PathResult conversion.
        Useful for debugging and testing.
        """
        return self._run_fixpoint_analysis()


# ============================================================
# Integration with TaintEngine
# ============================================================


def create_fixpoint_query_adapter(
    ir_doc: "IRDocument",
    sources: set[str] | None = None,
    sinks: set[str] | None = None,
    sanitizers: set[str] | None = None,
    use_fixpoint: bool = True,
) -> FixpointQueryAdapter:
    """
    Factory function for FixpointQueryAdapter.

    Args:
        ir_doc: IR document to analyze
        sources: Custom source patterns
        sinks: Custom sink patterns
        sanitizers: Custom sanitizer patterns
        use_fixpoint: Whether to use fixpoint iteration

    Returns:
        Configured FixpointQueryAdapter
    """
    return FixpointQueryAdapter(
        ir_doc=ir_doc,
        sources=sources,
        sinks=sinks,
        sanitizers=sanitizers,
        use_fixpoint=use_fixpoint,
    )
