"""
Adaptive Configuration (SOTA Risk Mitigation)

Auto-adjusts LocalFlow config based on codebase characteristics.
Mitigates performance overhead for large/complex functions.

Design:
- Heuristic-based: function size/complexity → config
- Conservative: prefer correctness over speed
- Observable: logs decisions for tuning
"""

from codegraph_engine.code_foundation.domain.type_inference.config import LocalFlowConfig
from codegraph_shared.infra.observability.logging import get_logger

logger = get_logger(__name__)


class AdaptiveLocalFlowConfig:
    """
    Adaptive LocalFlow configuration based on function characteristics.

    Mitigates performance overhead by adjusting max_iterations/max_union_size
    based on function size and complexity.

    Rules:
    - Small functions (<20 lines): full precision (max_iterations=5)
    - Medium functions (20-100 lines): balanced (max_iterations=3)
    - Large functions (>100 lines): fast (max_iterations=2)
    - High complexity (>10 branches): reduce union size

    Usage:
        adaptive = AdaptiveLocalFlowConfig()
        config = adaptive.get_config_for_function(func_node)
        inferencer = LocalFlowTypeInferencer(config=config)
    """

    def __init__(
        self,
        enable_adaptive: bool = True,
        default_config: LocalFlowConfig | None = None,
    ):
        """
        Initialize adaptive config.

        Args:
            enable_adaptive: Enable adaptive behavior (default: True)
            default_config: Fallback config when adaptive is disabled
        """
        self.enable_adaptive = enable_adaptive
        self.default_config = default_config or LocalFlowConfig()

    def get_config_for_function(self, func_node) -> LocalFlowConfig:
        """
        Get LocalFlow config adapted to function characteristics.

        Args:
            func_node: Function/Method IR Node

        Returns:
            Adapted LocalFlowConfig
        """
        if not self.enable_adaptive:
            return self.default_config

        # Extract characteristics
        span = func_node.span
        lines = span.end_line - span.start_line if span else 0

        # Control flow complexity
        cf_summary = func_node.control_flow_summary
        branches = cf_summary.branch_count if cf_summary else 0
        has_loop = cf_summary.has_loop if cf_summary else False

        # Adaptive rules
        if lines < 20:
            # Small function: full precision
            max_iterations = 5
            max_union_size = 8
        elif lines < 100:
            # Medium function: balanced
            max_iterations = 3
            max_union_size = 8
        else:
            # Large function: fast
            max_iterations = 2
            max_union_size = 6

        # High complexity: reduce union size (prevent explosion)
        if branches > 10:
            max_union_size = min(max_union_size, 6)

        # Loop: may need more iterations for convergence
        if has_loop and lines < 50:
            max_iterations = min(max_iterations + 1, 5)

        config = LocalFlowConfig(
            max_iterations=max_iterations,
            max_union_size=max_union_size,
            enable_call_propagation=True,
            enable_ternary=True,
            enable_binop=True,
        )

        logger.debug(
            "adaptive_local_flow_config",
            function=func_node.name,
            lines=lines,
            branches=branches,
            has_loop=has_loop,
            max_iterations=max_iterations,
            max_union_size=max_union_size,
        )

        return config

    def get_config_for_project(self, total_functions: int, total_lines: int) -> LocalFlowConfig:
        """
        Get project-wide config based on codebase size.

        Args:
            total_functions: Total number of functions
            total_lines: Total lines of code

        Returns:
            Project-wide LocalFlowConfig
        """
        if not self.enable_adaptive:
            return self.default_config

        avg_lines_per_func = total_lines / total_functions if total_functions > 0 else 0

        # Large codebase: prioritize speed
        if total_functions > 5000 or avg_lines_per_func > 100:
            return LocalFlowConfig(
                max_iterations=2,
                max_union_size=6,
                enable_call_propagation=True,
            )

        # Medium codebase: balanced
        if total_functions > 1000 or avg_lines_per_func > 50:
            return LocalFlowConfig(
                max_iterations=3,
                max_union_size=8,
                enable_call_propagation=True,
            )

        # Small codebase: full precision
        return LocalFlowConfig(
            max_iterations=5,
            max_union_size=8,
            enable_call_propagation=True,
        )
