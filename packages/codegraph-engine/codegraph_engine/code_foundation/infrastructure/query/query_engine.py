"""
QueryEngine

Main facade for Query DSL execution.

Architecture:
- Infrastructure layer (assembles all components)
- Public API for executing queries
- Handles PathQuery.any_path() and PathQuery.all_paths()
- Thread-safe query execution

Usage:
    engine = QueryEngine(ir_doc)
    query = (Q.Var("input") >> Q.Call("execute")).via(E.DFG)
    result = engine.execute(query)
"""

import hashlib
import threading
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantPropagationResult

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.types import QueryMode, SelectorType

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr, PathQuery
    from codegraph_engine.code_foundation.domain.query.options import QueryOptions
    from codegraph_engine.code_foundation.domain.query.results import PathSet, VerificationResult
    from codegraph_engine.code_foundation.infrastructure.query.container import QueryEngineContainer
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)


class QueryEngine:
    """
    Query Engine Facade

    Assembles all infrastructure components:
    - UnifiedGraphIndex
    - NodeMatcher
    - EdgeResolver
    - TraversalEngine
    - QueryExecutor

    Example:
        engine = QueryEngine(ir_doc)

        # Existential query
        paths = engine.execute_any_path(query)

        # Universal query
        verification = engine.execute_all_paths(query)
    """

    def __init__(self, ir_doc: "IRDocument", project_context=None):
        """
        Initialize Query Engine (Thread-safe)

        Args:
            ir_doc: IR document (must have all required data)
            project_context: Optional project context for full mode (RFC-021 Phase 2)

        Raises:
            ValueError: If ir_doc is invalid

        Thread Safety:
            All query execution methods are protected by RLock.
            Safe to use from multiple threads.

        RFC-021 Phase 1:
            - Added LRU cache (maxsize=100) for realtime/pr modes
            - Added project_context for full mode (Phase 2)
            - Added SCCP Baseline (RFC-021 Day 1)
        """
        if not ir_doc:
            raise ValueError("IRDocument cannot be None")

        self.ir_doc = ir_doc
        self.project_context = project_context

        # Thread safety lock (RLock allows recursive locking)
        self._lock = threading.RLock()

        # RFC-021 Phase 1: LRU Cache for performance
        # SOTA: Expanded cache size (100 → 500) for better hit rate
        self._cache: OrderedDict = OrderedDict()
        self._cache_maxsize = 500  # SOTA: 5x larger cache
        self._cache_max_bytes = 100 * 1024 * 1024  # SOTA: 100MB memory limit
        self._cache_total_bytes = 0

        # RFC-021 Day 1: SCCP Baseline Integration
        from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer

        self._sccp_analyzer = ConstantPropagationAnalyzer()
        self._sccp_result: "ConstantPropagationResult | None" = None

        # Build graph index
        from .graph_index import UnifiedGraphIndex

        self.graph = UnifiedGraphIndex(ir_doc)

        # Initialize components
        from .edge_resolver import EdgeResolver
        from .node_matcher import NodeMatcher
        from .query_executor import QueryExecutor
        from .traversal_engine import TraversalEngine

        # NodeMatcher with default TaintConfig (can be customized via DI)
        self.node_matcher = NodeMatcher(self.graph)
        self.edge_resolver = EdgeResolver(self.graph)
        self.traversal = TraversalEngine(self.graph, self.node_matcher, self.edge_resolver)
        self.executor = QueryExecutor(self.graph, self.node_matcher, self.edge_resolver, self.traversal)

        logger.info("query_engine_initialized", graph_stats=self.graph.get_stats())

    @classmethod
    def _from_container(cls, container: "QueryEngineContainer") -> "QueryEngine":
        """
        Create QueryEngine from DI Container (internal, thread-safe)

        Args:
            container: DI container with all dependencies

        Returns:
            Configured QueryEngine with thread safety
        """
        # Create instance without __init__
        engine = cls.__new__(cls)

        # Thread safety lock
        engine._lock = threading.RLock()

        # Inject dependencies from container
        engine.ir_doc = container.get_graph_index().ir_doc
        engine.graph = container.get_graph_index()
        engine.node_matcher = container.get_node_matcher()
        engine.edge_resolver = container.get_edge_resolver()
        engine.traversal = container.get_traversal_engine()
        engine.executor = container.get_query_executor()

        logger.info("query_engine_created_from_container")
        return engine

    def execute_any_path(self, query: "PathQuery") -> "PathSet":
        """
        Execute existential query (∃) - Thread-safe

        Args:
            query: Path query

        Returns:
            PathSet with found paths

        Thread Safety:
            Protected by RLock. Safe for concurrent execution.
        """
        with self._lock:
            return self.executor.execute_any_path(query)

    def execute_all_paths(self, query: "PathQuery") -> "VerificationResult":
        """
        Execute universal query (∀) - Thread-safe

        Args:
            query: Path query

        Returns:
            VerificationResult

        Thread Safety:
            Protected by RLock. Safe for concurrent execution.
        """
        with self._lock:
            return self.executor.execute_all_paths(query)

    def execute(self, query: "PathQuery") -> "PathSet | VerificationResult":
        """
        Execute query (dispatches to any_path by default) - Thread-safe

        Args:
            query: Path query

        Returns:
            PathSet or VerificationResult

        Thread Safety:
            Protected by RLock. Safe for concurrent execution.
        """
        with self._lock:
            return self.execute_any_path(query)

    def execute_flow(self, flow_expr: "FlowExpr", mode: QueryMode = QueryMode.PR, **overrides: Any) -> "PathSet":
        """
        Execute FlowExpr with mode-based routing (RFC-021 Phase 1)

        Args:
            flow_expr: Flow expression (source >> target)
            mode: Execution mode (QueryMode.REALTIME | QueryMode.PR | QueryMode.FULL)
            **overrides: QueryOptions overrides (e.g., max_depth=15)

        Returns:
            PathSet with discovered paths

        Modes:
            - REALTIME: <100ms (depth=3, paths=10, IDE)
            - PR: <5s (depth=10, paths=100, CI)
            - FULL: Minutes (depth=20, k-CFA, Alias) [Phase 2]

        Usage:
            ```python
            # Realtime (IDE)
            paths = engine.execute_flow(expr, mode=QueryMode.REALTIME)

            # PR check (CI)
            paths = engine.execute_flow(expr, mode=QueryMode.PR)

            # Custom
            paths = engine.execute_flow(expr, mode=QueryMode.PR, max_depth=15)
            ```

        Thread Safety:
            Protected by RLock. Safe for concurrent execution.

        Caching:
            Results cached with LRU(100) for realtime/pr modes.
        """
        with self._lock:
            start_time = time.time()

            # RFC-021 Phase 3.3: Exception Isolation (Graceful Degradation)
            #
            # 구분:
            # 1. User Errors (ValueError, TypeError) → 즉시 raise (사용자 책임)
            # 2. Analysis Errors (RecursionError, 분석 중 예외) → Graceful Degradation
            try:
                return self._execute_flow_internal(flow_expr, mode, overrides, start_time)
            except (ValueError, TypeError) as e:
                # User error: 즉시 raise (잘못된 mode, 누락된 context 등)
                logger.error("user_error", mode=mode, error=str(e))
                raise
            except RecursionError as e:
                # Analysis error: Graceful degradation
                logger.error("recursion_limit_hit", mode=mode, error=str(e))
                from codegraph_engine.code_foundation.domain.query.results import PathSet, StopReason

                return PathSet(
                    paths=[],
                    stop_reason=StopReason.ERROR,
                    elapsed_ms=int((time.time() - start_time) * 1000),
                    nodes_visited=0,
                    diagnostics=(
                        f"recursion_error: {type(e).__name__}",
                        f"mode: {mode.value if hasattr(mode, 'value') else mode}",
                    ),
                )
            except Exception as e:
                # Other analysis errors: Graceful degradation
                logger.exception("query_engine_error", mode=mode.value if hasattr(mode, "value") else mode)
                from codegraph_engine.code_foundation.domain.query.results import PathSet, StopReason

                # Return partial results if available
                partial_paths = getattr(self, "_partial_results", [])
                return PathSet(
                    paths=partial_paths,
                    stop_reason=StopReason.ERROR,
                    elapsed_ms=int((time.time() - start_time) * 1000),
                    nodes_visited=0,
                    diagnostics=(
                        f"error: {type(e).__name__}: {str(e)[:200]}",
                        f"mode: {mode.value if hasattr(mode, 'value') else mode}",
                    ),
                )

    def _execute_flow_internal(
        self, flow_expr: "FlowExpr", mode: QueryMode, overrides: dict, start_time: float
    ) -> "PathSet":
        """
        Internal execute_flow logic (without exception handling)

        Args:
            flow_expr: Flow expression
            mode: QueryMode enum
            overrides: QueryOptions overrides
            start_time: Start timestamp

        Returns:
            PathSet
        """
        # 0. RFC-021 Day 1: Run SCCP Baseline (모든 모드에서 실행)
        sccp_result = self._run_sccp_baseline()

        # 1. Get or build QueryOptions
        options = self._merge_options(mode, overrides)

        # 2. Check cache (realtime/pr only)
        if mode in (QueryMode.REALTIME, QueryMode.PR):
            cache_key = self._make_cache_key(flow_expr, mode, options)
            if cache_key in self._cache:
                logger.debug("cache_hit", mode=mode.value if hasattr(mode, "value") else mode, cache_key=cache_key[:16])
                return self._cache[cache_key]

        # 3. Mode routing
        if mode in (QueryMode.REALTIME, QueryMode.PR):
            # Use TraversalEngine (BFS/DFS)
            from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr, PathQuery

            # ⭐ SOTA: Support both FlowExpr and PathQuery (for sanitizer barriers)
            if isinstance(flow_expr, PathQuery):
                path_query = flow_expr
            elif isinstance(flow_expr, FlowExpr):
                path_query = PathQuery.from_flow_expr(flow_expr)
            else:
                # Fallback: try to convert
                path_query = PathQuery.from_flow_expr(flow_expr)

            result = self.execute_any_path(path_query)

            # Update metrics (RFC-021 Phase 1)
            elapsed_ms = int((time.time() - start_time) * 1000)
            from codegraph_engine.code_foundation.domain.query.results import PathSet, StopReason

            # Wrap legacy result with new fields
            result = PathSet(
                paths=result.paths,
                stop_reason=StopReason.COMPLETE if result.complete else StopReason.TIMEOUT,
                elapsed_ms=elapsed_ms,
                nodes_visited=0,  # TraversalEngine doesn't track this yet
                diagnostics=(f"mode: {mode.value if hasattr(mode, 'value') else mode}", f"elapsed_ms: {elapsed_ms}"),
            )

        elif mode == QueryMode.FULL:
            # RFC-021 Phase 2: DeepAnalyzer
            if not self.project_context:
                raise ValueError(
                    "full mode requires project_context. Pass project_context to QueryEngine(..., project_context=ctx)"
                )

            from codegraph_engine.code_foundation.infrastructure.query.deep_analyzer import DeepAnalyzer

            analyzer = DeepAnalyzer(self.project_context)
            result = analyzer.analyze(flow_expr, options)
        else:
            raise ValueError(f"Unknown mode: {mode}. Use QueryMode.REALTIME, QueryMode.PR, or QueryMode.FULL")

        # 4. Cache result (realtime/pr only) - CRITICAL FIX: Indentation!
        if mode in (QueryMode.REALTIME, QueryMode.PR):
            # Estimate PathSet size
            result_size = self._estimate_pathset_size(result)

            self._cache[cache_key] = result
            self._cache_total_bytes += result_size

            # P1: Size-aware eviction (count + memory)
            while len(self._cache) > self._cache_maxsize or self._cache_total_bytes > self._cache_max_bytes:
                if len(self._cache) == 0:
                    break
                evicted_key, evicted_value = self._cache.popitem(last=False)
                evicted_size = self._estimate_pathset_size(evicted_value)
                self._cache_total_bytes -= evicted_size

                logger.debug(
                    "cache_evicted",
                    key=evicted_key[:16],
                    size_bytes=evicted_size,
                    total_bytes=self._cache_total_bytes,
                )

        return result

    def _merge_options(self, mode: QueryMode, overrides: dict) -> "QueryOptions":
        """
        Merge mode preset with overrides

        Args:
            mode: QueryMode enum
            overrides: User-provided overrides

        Returns:
            Merged QueryOptions

        RFC-021: Unknown overrides are logged but don't raise errors (API stability)
        """
        from codegraph_engine.code_foundation.domain.query.options import PRESETS, QueryOptions

        # Use mode.value for PRESETS lookup (PRESETS uses string keys)
        mode_key = mode.value if hasattr(mode, "value") else mode
        if mode_key not in PRESETS:
            raise ValueError(f"Unknown mode: {mode}. Available: {list(PRESETS.keys())}")

        preset = PRESETS[mode_key]

        # Filter known options
        known_fields = set(QueryOptions.__dataclass_fields__.keys())
        unknown_keys = set(overrides.keys()) - known_fields
        if unknown_keys:
            logger.warning("unknown_query_options", keys=list(unknown_keys), mode=mode)

        valid_overrides = {k: v for k, v in overrides.items() if k in known_fields}

        return preset.replace(**valid_overrides)

    def _make_cache_key(self, flow_expr: "FlowExpr", mode: QueryMode, options: "QueryOptions") -> str:
        """
        Generate stable cache key (RFC-021 P1 Fix)

        Args:
            flow_expr: Flow expression
            mode: Mode name
            options: Query options

        Returns:
            Stable cache key (deterministic for same inputs)

        Key format: "{expr_parts}:{mode}:{options_fields}"

        P1 Fix:
            str(flow_expr)는 object repr 의존 → 불안정
            → 구조적 동등성 기반 (source/target name + edge types)

        P2 Fix (SOTA):
            PathQuery는 source/target이 없고 flow 속성에 FlowExpr 보유
            → flow 속성에서 FlowExpr 추출하여 cache key 생성
        """
        # 🔥 SOTA FIX: PathQuery → FlowExpr 추출
        actual_flow = flow_expr
        if hasattr(flow_expr, "flow"):
            actual_flow = flow_expr.flow

        # Stable FlowExpr representation
        expr_parts = []
        if hasattr(actual_flow, "source"):
            source = actual_flow.source
            source_repr = self._selector_to_cache_key(source)
            expr_parts.append(source_repr)

        if hasattr(actual_flow, "target"):
            target = actual_flow.target
            target_repr = self._selector_to_cache_key(target)
            expr_parts.append(target_repr)

        # 🔥 SOTA FIX: edge_type 사용 (via_edges가 아님)
        if hasattr(actual_flow, "edge_type") and actual_flow.edge_type:
            expr_parts.append(f"via:{str(actual_flow.edge_type)}")

        expr_str = ">>".join(expr_parts)

        # Stable QueryOptions representation
        options_parts = [
            f"depth:{options.max_depth}",
            f"paths:{options.max_paths}",
            f"nodes:{options.max_nodes}",
            f"timeout:{options.timeout_ms}",
            f"ctx:{options.context_sensitive}",
            f"k:{options.k_limit}",
            f"alias:{options.alias_analysis}",
        ]
        options_str = "|".join(options_parts)

        # Combine (use mode.value for stable key)
        mode_str = mode.value if hasattr(mode, "value") else str(mode)
        combined = f"{expr_str}::{mode_str}::{options_str}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _selector_to_cache_key(self, selector: Any) -> str:
        """
        Convert selector to stable cache key representation.

        Handles UNION selectors by including all operands in the key.

        Args:
            selector: Node selector (Q.Call, Q.Union, etc.)

        Returns:
            Stable string representation for cache key
        """
        selector_type = getattr(selector, "selector_type", "unknown")
        # Normalize to string value for comparison
        selector_type_value = selector_type.value if hasattr(selector_type, "value") else str(selector_type)

        # Handle UNION selector: include all operand names
        if selector_type_value == SelectorType.UNION.value:
            attrs = getattr(selector, "attrs", {})
            operands = attrs.get("operands", [])
            if operands:
                operand_names = sorted(getattr(op, "name", None) or str(op) for op in operands)
                return f"union:[{','.join(operand_names)}]"
            return "union:[]"

        # Handle regular selectors
        name = getattr(selector, "name", None) or "*"
        return f"{selector_type_value}:{name}"

    def _run_sccp_baseline(self) -> "ConstantPropagationResult | None":
        """
        Run SCCP Baseline Analysis (RFC-021 Day 1)

        Returns:
            ConstantPropagationResult or None if prerequisites missing

        Raises:
            RuntimeError: If SCCP analysis fails unexpectedly

        Features:
            - Constant propagation (x = 10 → x is Const(10))
            - Unreachable block detection
            - Constant condition evaluation (if x > 5, x=10 → True)

        Performance:
            - Cached after first run (O(1) subsequent calls)
            - First run: ~2-10ms (CFG size dependent)
            - Measured and logged

        Thread Safety:
            Protected by _lock (called from execute_flow)

        Observability:
            - Logs skip reasons (expected: no CFG/DFG)
            - Logs success with metrics + timing
            - Re-raises unexpected failures (no silent fail)
        """
        # Check cache
        if self._sccp_result is not None:
            return self._sccp_result

        # Check prerequisites (soft fail - expected cases)
        if not self.ir_doc.cfg_blocks:
            logger.info("sccp_baseline_skipped", reason="no_cfg_blocks", snapshot_id=self.ir_doc.snapshot_id)
            return None

        if not self.ir_doc.dfg_snapshot:
            logger.info("sccp_baseline_skipped", reason="no_dfg_snapshot", snapshot_id=self.ir_doc.snapshot_id)
            return None

        try:
            # Run SCCP with timing
            import time

            start = time.perf_counter()
            result = self._sccp_analyzer.analyze(self.ir_doc)
            elapsed_ms = (time.perf_counter() - start) * 1000

            self._sccp_result = result

            logger.info(
                "sccp_baseline_complete",
                snapshot_id=self.ir_doc.snapshot_id,
                constants_found=result.constants_found,
                unreachable_blocks=len(result.unreachable_blocks),
                reachable_blocks=len(result.reachable_blocks),
                elapsed_ms=round(elapsed_ms, 2),
            )

            return result

        except Exception as e:
            # Hard fail - unexpected error (don't silent fail!)
            logger.error(
                "sccp_baseline_failed",
                snapshot_id=self.ir_doc.snapshot_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            # Re-raise for visibility
            raise RuntimeError(f"SCCP baseline analysis failed: {e}") from e

    def invalidate_cache(self):
        """
        Invalidate all cached results (RFC-021 Phase 1)

        Call when ir_doc changes (e.g., ShadowFS transaction).

        RFC-021 Day 1 FIX:
            - Clear QueryEngine SCCP cache
            - Clear TraversalEngine SCCP cache (critical!)
            - Reload SCCP on next query

        Thread Safety:
            Protected by _lock
        """
        with self._lock:
            self._cache.clear()
            self._cache_total_bytes = 0
            self._sccp_result = None  # RFC-021 Day 1: Clear SCCP cache

            # RFC-021 Day 1 FIX: Clear ConstantPropagationAnalyzer cache
            # ConstantPropagationAnalyzer has its own cache by snapshot_id
            # Must clear it to force re-analysis after ir_doc changes
            if hasattr(self, "_sccp_analyzer") and self._sccp_analyzer:
                self._sccp_analyzer.clear_cache()

            # RFC-021 Day 1 FIX: Invalidate TraversalEngine SCCP cache
            # TraversalEngine uses lazy loading, so just reset the flag
            if hasattr(self, "traversal") and self.traversal:
                self.traversal._sccp_result = None
                self.traversal._sccp_loaded = False  # Force reload on next use

            logger.info("cache_invalidated", sccp_invalidated=True)

    def _estimate_pathset_size(self, pathset: "PathSet") -> int:
        """
        Estimate PathSet memory size (RFC-021 P1 Fix)

        Args:
            pathset: PathSet to measure

        Returns:
            Estimated size in bytes

        Estimation:
            - PathResult: ~1KB base
            - UnifiedNode: ~200 bytes
            - UnifiedEdge: ~100 bytes
            - diagnostics: ~50 bytes per entry
        """
        base_size = 1024  # PathSet overhead

        for path in pathset.paths:
            base_size += 1024  # PathResult overhead
            base_size += len(path.nodes) * 200  # Nodes
            base_size += len(path.edges) * 100  # Edges

        base_size += len(pathset.diagnostics) * 50  # Diagnostics

        return base_size

    def get_stats(self) -> dict:
        """
        Get query engine statistics - Thread-safe

        Returns:
            Statistics dictionary

        Thread Safety:
            Protected by RLock. Safe for concurrent access.
        """
        with self._lock:
            return {
                "graph": self.graph.get_stats(),
            }
