"""
Query Engine Container - DI Container (L11급 SOTA)

Dependency Injection Container using Factory + Builder patterns.

Provides:
- Component lifecycle management
- Dependency resolution
- Configuration management
- Testability (mock injection)

Patterns:
- Factory: Component creation
- Builder: Fluent configuration
- Singleton: Shared instances

SOLID:
- S: Container만 관리
- O: 새 컴포넌트 추가 용이
- L: 인터페이스 기반
- I: Minimal API
- D: Port 기반 주입
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

    from .edge_resolver import EdgeResolver
    from .graph_index import UnifiedGraphIndex
    from .node_matcher import NodeMatcher
    from .query_engine import QueryEngine
    from .query_executor import QueryExecutor
    from .repositories import IndexBackedGraphRepository
    from .traversal_engine import TraversalEngine

logger = get_logger(__name__)


@dataclass
class QueryEngineConfig:
    """
    Query engine configuration

    All configuration in one place for easy testing.
    """

    # Safety limits
    default_max_depth: int = 10
    default_max_paths: int = 100
    default_max_nodes: int = 10000
    default_timeout_ms: int = 30000

    # Performance tuning
    enable_caching: bool = True
    enable_query_optimization: bool = True

    # Debugging
    enable_query_logging: bool = False
    enable_performance_metrics: bool = False

    # Additional settings
    extra: dict = field(default_factory=dict)


class QueryEngineContainer:
    """
    DI Container for Query Engine

    Manages component lifecycle and dependencies.

    Usage:
        # Production
        container = QueryEngineContainer.create(ir_doc)
        engine = container.get_query_engine()

        # Testing (with mocks)
        container = (QueryEngineContainer.builder()
            .with_graph_index(mock_index)
            .with_node_matcher(mock_matcher)
            .build())
        engine = container.get_query_engine()

    Architecture:
        Container
            ├─ UnifiedGraphIndex
            ├─ NodeMatcher
            ├─ EdgeResolver
            ├─ TraversalEngine
            ├─ QueryExecutor
            ├─ GraphRepository
            └─ QueryEngine (facade)
    """

    def __init__(
        self,
        config: QueryEngineConfig | None = None,
        # Components (for testing)
        graph_index: "UnifiedGraphIndex | None" = None,
        node_matcher: "NodeMatcher | None" = None,
        edge_resolver: "EdgeResolver | None" = None,
        traversal_engine: "TraversalEngine | None" = None,
        query_executor: "QueryExecutor | None" = None,
        repository: "IndexBackedGraphRepository | None" = None,
    ):
        """
        Initialize container with lifecycle management

        Args:
            config: Configuration
            graph_index: Graph index (for testing)
            node_matcher: Node matcher (for testing)
            edge_resolver: Edge resolver (for testing)
            traversal_engine: Traversal engine (for testing)
            query_executor: Query executor (for testing)
            repository: Repository (for testing)

        Usage:
            # With context manager (recommended)
            with QueryEngineContainer.create(ir_doc) as container:
                engine = container.get_query_engine()
                result = engine.execute(query)
            # Auto cleanup

            # Manual lifecycle
            container = QueryEngineContainer.create(ir_doc)
            try:
                # ... use container
            finally:
                container.close()
        """
        self.config = config or QueryEngineConfig()

        # Injected components (or None)
        self._graph_index = graph_index
        self._node_matcher = node_matcher
        self._edge_resolver = edge_resolver
        self._traversal_engine = traversal_engine
        self._query_executor = query_executor
        self._repository = repository

        # Lifecycle state
        self._closed = False

        logger.info("query_engine_container_initialized", config=self.config)

    @classmethod
    def create(cls, ir_doc: "IRDocument", config: QueryEngineConfig | None = None) -> "QueryEngineContainer":
        """
        Create container with default components (Factory)

        Args:
            ir_doc: IR document
            config: Configuration

        Returns:
            Configured container
        """
        from .edge_resolver import EdgeResolver
        from .graph_index import UnifiedGraphIndex
        from .node_matcher import NodeMatcher
        from .query_executor import QueryExecutor
        from .repositories import IndexBackedGraphRepository
        from .traversal_engine import TraversalEngine

        # Build components
        graph_index = UnifiedGraphIndex(ir_doc)
        # NodeMatcher with default TaintConfig (extensible in future)
        node_matcher = NodeMatcher(graph_index)
        edge_resolver = EdgeResolver(graph_index)
        traversal_engine = TraversalEngine(graph_index, node_matcher, edge_resolver)
        query_executor = QueryExecutor(graph_index, node_matcher, edge_resolver, traversal_engine)
        repository = IndexBackedGraphRepository(graph_index)

        return cls(
            config=config,
            graph_index=graph_index,
            node_matcher=node_matcher,
            edge_resolver=edge_resolver,
            traversal_engine=traversal_engine,
            query_executor=query_executor,
            repository=repository,
        )

    @classmethod
    def builder(cls) -> "QueryEngineContainerBuilder":
        """
        Get builder for fluent configuration

        Returns:
            Container builder
        """
        return QueryEngineContainerBuilder()

    # ============================================================
    # Component Accessors
    # ============================================================

    def get_graph_index(self) -> "UnifiedGraphIndex":
        """Get graph index (or raise if not configured)"""
        if self._graph_index is None:
            raise ValueError("GraphIndex not configured. Use .create() or .builder()")
        return self._graph_index

    def get_node_matcher(self) -> "NodeMatcher":
        """Get node matcher (lazy creation)"""
        if self._node_matcher is None:
            from .node_matcher import NodeMatcher

            self._node_matcher = NodeMatcher(self.get_graph_index())
        return self._node_matcher

    def get_edge_resolver(self) -> "EdgeResolver":
        """Get edge resolver (lazy creation)"""
        if self._edge_resolver is None:
            from .edge_resolver import EdgeResolver

            self._edge_resolver = EdgeResolver(self.get_graph_index())
        return self._edge_resolver

    def get_traversal_engine(self) -> "TraversalEngine":
        """Get traversal engine (lazy creation)"""
        if self._traversal_engine is None:
            from .traversal_engine import TraversalEngine

            self._traversal_engine = TraversalEngine(
                self.get_graph_index(), self.get_node_matcher(), self.get_edge_resolver()
            )
        return self._traversal_engine

    def get_query_executor(self) -> "QueryExecutor":
        """Get query executor (lazy creation)"""
        if self._query_executor is None:
            from .query_executor import QueryExecutor

            self._query_executor = QueryExecutor(
                self.get_graph_index(), self.get_node_matcher(), self.get_edge_resolver(), self.get_traversal_engine()
            )
        return self._query_executor

    def get_repository(self) -> "IndexBackedGraphRepository":
        """Get repository (lazy creation)"""
        if self._repository is None:
            from .repositories import IndexBackedGraphRepository

            self._repository = IndexBackedGraphRepository(self.get_graph_index())
        return self._repository

    def get_query_engine(self) -> "QueryEngine":
        """
        Get query engine (facade)

        Returns:
            QueryEngine configured with all components
        """
        if self._closed:
            raise RuntimeError("Container is closed")

        from .query_engine import QueryEngine

        # QueryEngine directly uses executor
        # In future: can inject via constructor
        return QueryEngine._from_container(self)

    # ============================================================
    # Lifecycle Management
    # ============================================================

    def close(self) -> None:
        """
        Close container and cleanup resources

        Cleanup actions:
        - Clear repository cache
        - Release component references
        - Mark as closed

        Safe to call multiple times (idempotent).
        """
        if self._closed:
            return

        try:
            # Cleanup repository cache
            if self._repository:
                self._repository.clear_cache()

            # Future: Close any open connections, files, etc
            # if self._graph_index:
            #     self._graph_index.close()

            self._closed = True
            logger.info("query_engine_container_closed")

        except Exception as e:
            logger.error("error_closing_container", error=str(e))
            raise

    def is_closed(self) -> bool:
        """Check if container is closed"""
        return self._closed

    def __enter__(self) -> "QueryEngineContainer":
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit (auto cleanup)"""
        self.close()
        return False  # Don't suppress exceptions

    def __del__(self):
        """Destructor - warn if not properly closed"""
        if not self._closed:
            logger.warning(
                "query_engine_container_not_closed",
                message="Container was not properly closed. Use 'with' statement or call .close()",
            )
            try:
                self.close()
            except Exception:
                pass  # Suppress errors in __del__


class QueryEngineContainerBuilder:
    """
    Builder for QueryEngineContainer (Fluent API)

    Usage:
        container = (QueryEngineContainer.builder()
            .with_config(config)
            .with_graph_index(mock_index)
            .with_node_matcher(mock_matcher)
            .build())
    """

    def __init__(self):
        self._config: QueryEngineConfig | None = None
        self._graph_index: UnifiedGraphIndex | None = None
        self._node_matcher: NodeMatcher | None = None
        self._edge_resolver: EdgeResolver | None = None
        self._traversal_engine: TraversalEngine | None = None
        self._query_executor: QueryExecutor | None = None
        self._repository: IndexBackedGraphRepository | None = None

    def with_config(self, config: QueryEngineConfig) -> "QueryEngineContainerBuilder":
        """Set configuration"""
        self._config = config
        return self

    def with_graph_index(self, graph_index: "UnifiedGraphIndex") -> "QueryEngineContainerBuilder":
        """Set graph index"""
        self._graph_index = graph_index
        return self

    def with_node_matcher(self, node_matcher: "NodeMatcher") -> "QueryEngineContainerBuilder":
        """Set node matcher"""
        self._node_matcher = node_matcher
        return self

    def with_edge_resolver(self, edge_resolver: "EdgeResolver") -> "QueryEngineContainerBuilder":
        """Set edge resolver"""
        self._edge_resolver = edge_resolver
        return self

    def with_traversal_engine(self, traversal_engine: "TraversalEngine") -> "QueryEngineContainerBuilder":
        """Set traversal engine"""
        self._traversal_engine = traversal_engine
        return self

    def with_query_executor(self, query_executor: "QueryExecutor") -> "QueryEngineContainerBuilder":
        """Set query executor"""
        self._query_executor = query_executor
        return self

    def with_repository(self, repository: "IndexBackedGraphRepository") -> "QueryEngineContainerBuilder":
        """Set repository"""
        self._repository = repository
        return self

    def build(self) -> QueryEngineContainer:
        """Build container"""
        return QueryEngineContainer(
            config=self._config,
            graph_index=self._graph_index,
            node_matcher=self._node_matcher,
            edge_resolver=self._edge_resolver,
            traversal_engine=self._traversal_engine,
            query_executor=self._query_executor,
            repository=self._repository,
        )
