"""
Agent configuration helpers.

Provides utilities for configuring agent system with optional dependencies.
"""

from typing import Any

from src.common.observability import get_logger

logger = get_logger(__name__)


class DependencyChecker:
    """
    Check availability of optional dependencies.

    Helps gracefully handle missing dependencies in agent modes.
    """

    @staticmethod
    def check_llm(llm_client: Any) -> bool:
        """Check if LLM client is available and functional."""
        if llm_client is None:
            return False

        # Check if it has the required methods
        return hasattr(llm_client, "complete")

    @staticmethod
    def check_symbol_index(symbol_index: Any) -> bool:
        """Check if symbol index is available and functional."""
        if symbol_index is None:
            return False

        # Check if it has the required methods
        return hasattr(symbol_index, "search_symbols")

    @staticmethod
    def check_graph_client(graph_client: Any) -> bool:
        """Check if graph client is available and functional."""
        if graph_client is None:
            return False

        # Check if it has the required methods
        return hasattr(graph_client, "execute_query")

    @staticmethod
    def log_missing_dependency(component: str, fallback: str = "basic functionality"):
        """Log warning about missing dependency."""
        logger.warning(f"{component} not available, using {fallback}")


class AgentModeConfig:
    """
    Configuration for agent mode with dependency checking.

    Helps modes gracefully handle missing dependencies.
    """

    def __init__(
        self,
        llm_client: Any = None,
        symbol_index: Any = None,
        graph_client: Any = None,
        chunk_store: Any = None,
    ):
        """
        Initialize mode configuration.

        Args:
            llm_client: Optional LLM client
            symbol_index: Optional symbol index
            graph_client: Optional graph client
            chunk_store: Optional chunk store
        """
        self.llm_client = llm_client
        self.symbol_index = symbol_index
        self.graph_client = graph_client
        self.chunk_store = chunk_store

        # Check dependencies
        self.has_llm = DependencyChecker.check_llm(llm_client)
        self.has_symbol_index = DependencyChecker.check_symbol_index(symbol_index)
        self.has_graph = DependencyChecker.check_graph_client(graph_client)
        self.has_chunk_store = chunk_store is not None

        # Log missing dependencies
        if not self.has_llm:
            DependencyChecker.log_missing_dependency("LLM client", "rule-based fallback")
        if not self.has_symbol_index:
            DependencyChecker.log_missing_dependency("Symbol index", "pattern matching")
        if not self.has_graph:
            DependencyChecker.log_missing_dependency("Graph client", "basic analysis")

    def get_capability_level(self) -> str:
        """
        Get capability level based on available dependencies.

        Returns:
            "full" if all dependencies available,
            "partial" if some available,
            "basic" if none available
        """
        available_count = sum([self.has_llm, self.has_symbol_index, self.has_graph, self.has_chunk_store])

        if available_count == 4:
            return "full"
        elif available_count >= 2:
            return "partial"
        else:
            return "basic"

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"AgentModeConfig("
            f"llm={self.has_llm}, "
            f"symbol={self.has_symbol_index}, "
            f"graph={self.has_graph}, "
            f"chunks={self.has_chunk_store}, "
            f"level={self.get_capability_level()})"
        )
