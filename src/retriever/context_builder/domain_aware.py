"""
Domain-Aware Context Builder v2

Layer-aware context construction that orders chunks based on architectural patterns.
Implements Phase 3 Action 17-1 from the retrieval execution plan.

Strategy:
- For API queries: Order as router → handler → service → store
- For different bounded contexts: Apply differential priorities
- Recognize common architectural patterns (MVC, layered, microservices)
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ArchitecturalLayer(str, Enum):
    """Common architectural layers."""

    # Web/API layers
    ROUTER = "router"  # HTTP routes, URL routing
    HANDLER = "handler"  # Request handlers, controllers
    MIDDLEWARE = "middleware"  # Middleware, filters
    SERVICE = "service"  # Business logic, services
    REPOSITORY = "repository"  # Data access, repositories
    MODEL = "model"  # Domain models, entities
    STORE = "store"  # Database, storage
    UTIL = "util"  # Utilities, helpers

    # Application layers
    ENTRYPOINT = "entrypoint"  # Main, app initialization
    CONFIG = "config"  # Configuration
    INTERFACE = "interface"  # Public API, interfaces

    # Testing
    TEST = "test"  # Tests
    FIXTURE = "fixture"  # Test fixtures, mocks

    # Unknown
    UNKNOWN = "unknown"


# Layer priority for different query types
LAYER_PRIORITIES = {
    # API/Web query: Want to see flow from router to store
    "api_flow": {
        ArchitecturalLayer.ROUTER: 10,
        ArchitecturalLayer.HANDLER: 9,
        ArchitecturalLayer.MIDDLEWARE: 7,
        ArchitecturalLayer.SERVICE: 8,
        ArchitecturalLayer.REPOSITORY: 6,
        ArchitecturalLayer.STORE: 5,
        ArchitecturalLayer.MODEL: 4,
        ArchitecturalLayer.UTIL: 2,
        ArchitecturalLayer.TEST: 1,
    },
    # Implementation query: Want business logic first
    "implementation": {
        ArchitecturalLayer.SERVICE: 10,
        ArchitecturalLayer.REPOSITORY: 9,
        ArchitecturalLayer.MODEL: 8,
        ArchitecturalLayer.HANDLER: 7,
        ArchitecturalLayer.ROUTER: 6,
        ArchitecturalLayer.UTIL: 5,
        ArchitecturalLayer.STORE: 4,
        ArchitecturalLayer.TEST: 2,
    },
    # Data/Model query: Want models and data access first
    "data": {
        ArchitecturalLayer.MODEL: 10,
        ArchitecturalLayer.REPOSITORY: 9,
        ArchitecturalLayer.STORE: 8,
        ArchitecturalLayer.SERVICE: 7,
        ArchitecturalLayer.HANDLER: 5,
        ArchitecturalLayer.UTIL: 4,
        ArchitecturalLayer.TEST: 2,
    },
    # Entrypoint query: Want main/config first
    "entrypoint": {
        ArchitecturalLayer.ENTRYPOINT: 10,
        ArchitecturalLayer.CONFIG: 9,
        ArchitecturalLayer.ROUTER: 8,
        ArchitecturalLayer.INTERFACE: 7,
        ArchitecturalLayer.SERVICE: 6,
        ArchitecturalLayer.MODEL: 5,
        ArchitecturalLayer.UTIL: 3,
        ArchitecturalLayer.TEST: 1,
    },
}

# Path patterns for layer detection
LAYER_PATTERNS = {
    ArchitecturalLayer.ROUTER: [
        r"/routes?/",
        r"/routing/",
        r"router\.py$",
        r"routes\.py$",
        r"urls\.py$",
        r"api/.*\.py$",
    ],
    ArchitecturalLayer.HANDLER: [
        r"/handlers?/",
        r"/controllers?/",
        r"handler\.py$",
        r"controller\.py$",
        r"views?\.py$",
    ],
    ArchitecturalLayer.MIDDLEWARE: [
        r"/middleware/",
        r"middleware\.py$",
        r"filters?\.py$",
    ],
    ArchitecturalLayer.SERVICE: [
        r"/services?/",
        r"/business/",
        r"/logic/",
        r"service\.py$",
        r"_service\.py$",
    ],
    ArchitecturalLayer.REPOSITORY: [
        r"/repositories?/",
        r"/repos?/",
        r"/dao/",
        r"repository\.py$",
        r"_repository\.py$",
        r"dao\.py$",
    ],
    ArchitecturalLayer.MODEL: [
        r"/models?/",
        r"/entities?/",
        r"/domain/",
        r"model\.py$",
        r"models\.py$",
        r"entity\.py$",
        r"schema\.py$",
    ],
    ArchitecturalLayer.STORE: [
        r"/storage/",
        r"/database/",
        r"/db/",
        r"store\.py$",
        r"database\.py$",
        r"db\.py$",
    ],
    ArchitecturalLayer.UTIL: [
        r"/utils?/",
        r"/helpers?/",
        r"/common/",
        r"util\.py$",
        r"utils\.py$",
        r"helper\.py$",
        r"helpers\.py$",
    ],
    ArchitecturalLayer.ENTRYPOINT: [
        r"main\.py$",
        r"__main__\.py$",
        r"app\.py$",
        r"server\.py$",
        r"index\.py$",
    ],
    ArchitecturalLayer.CONFIG: [
        r"/config/",
        r"config\.py$",
        r"settings\.py$",
        r"constants\.py$",
    ],
    ArchitecturalLayer.INTERFACE: [
        r"/interface/",
        r"/api/",
        r"/ports/",
        r"interface\.py$",
        r"ports\.py$",
    ],
    ArchitecturalLayer.TEST: [
        r"/tests?/",
        r"test_.*\.py$",
        r".*_test\.py$",
    ],
    ArchitecturalLayer.FIXTURE: [
        r"/fixtures?/",
        r"/mocks?/",
        r"fixtures?\.py$",
        r"mocks?\.py$",
    ],
}


@dataclass
class LayeredChunk:
    """Chunk with detected architectural layer."""

    chunk_id: str
    content: str
    file_path: str
    layer: ArchitecturalLayer
    layer_priority: int
    original_score: float
    adjusted_score: float
    metadata: dict[str, Any]


class DomainAwareContextBuilder:
    """
    Domain-aware context builder that orders chunks by architectural layers.

    Recognizes common patterns and reorders chunks to provide better context flow.
    """

    def __init__(self):
        """Initialize domain-aware context builder."""
        self.layer_patterns = LAYER_PATTERNS
        self.layer_priorities = LAYER_PRIORITIES

    def build_ordered_context(
        self,
        chunks: list[dict[str, Any]],
        query: str,
        query_type: str = "implementation",
        boost_factor: float = 0.2,
    ) -> list[LayeredChunk]:
        """
        Build context with layer-aware ordering.

        Args:
            chunks: Input chunks with scores
            query: User query (for context)
            query_type: Type of query (api_flow, implementation, data, entrypoint)
            boost_factor: How much to boost scores based on layer priority (0-1)

        Returns:
            Ordered chunks with layer information
        """
        # Detect layers for all chunks
        layered_chunks = []
        for chunk in chunks:
            layer = self._detect_layer(chunk.get("file_path", ""))
            priority = self._get_layer_priority(layer, query_type)

            original_score = chunk.get("score", 0.0)
            adjusted_score = self._adjust_score(original_score, priority, boost_factor)

            layered_chunks.append(
                LayeredChunk(
                    chunk_id=chunk["chunk_id"],
                    content=chunk.get("content", ""),
                    file_path=chunk.get("file_path", ""),
                    layer=layer,
                    layer_priority=priority,
                    original_score=original_score,
                    adjusted_score=adjusted_score,
                    metadata=chunk.get("metadata", {}),
                )
            )

        # Sort by adjusted score (which includes layer priority boost)
        layered_chunks.sort(key=lambda c: c.adjusted_score, reverse=True)

        logger.info(
            f"Domain-aware ordering: {len(layered_chunks)} chunks, "
            f"query_type={query_type}, "
            f"layer_distribution={self._get_layer_distribution(layered_chunks)}"
        )

        return layered_chunks

    def _detect_layer(self, file_path: str) -> ArchitecturalLayer:
        """
        Detect architectural layer from file path.

        Args:
            file_path: File path

        Returns:
            Detected layer
        """
        # Check each layer's patterns
        for layer, patterns in self.layer_patterns.items():
            for pattern in patterns:
                if re.search(pattern, file_path, re.IGNORECASE):
                    return layer

        return ArchitecturalLayer.UNKNOWN

    def _get_layer_priority(
        self, layer: ArchitecturalLayer, query_type: str
    ) -> int:
        """
        Get layer priority for query type.

        Args:
            layer: Architectural layer
            query_type: Query type

        Returns:
            Priority (higher = more important)
        """
        priorities = self.layer_priorities.get(query_type, {})
        return priorities.get(layer, 0)

    def _adjust_score(
        self, original_score: float, priority: int, boost_factor: float
    ) -> float:
        """
        Adjust score based on layer priority.

        Args:
            original_score: Original retrieval score
            priority: Layer priority (0-10)
            boost_factor: How much to boost (0-1)

        Returns:
            Adjusted score
        """
        # Normalize priority to 0-1
        normalized_priority = priority / 10.0

        # Boost = boost_factor * normalized_priority
        boost = boost_factor * normalized_priority

        # Adjusted score = original * (1 + boost)
        return original_score * (1.0 + boost)

    def _get_layer_distribution(
        self, chunks: list[LayeredChunk]
    ) -> dict[str, int]:
        """
        Get distribution of layers in chunks.

        Args:
            chunks: Layered chunks

        Returns:
            Layer counts
        """
        distribution = {}
        for chunk in chunks:
            layer_name = chunk.layer.value
            distribution[layer_name] = distribution.get(layer_name, 0) + 1
        return distribution

    def infer_query_type(self, query: str) -> str:
        """
        Infer query type from query text.

        Args:
            query: User query

        Returns:
            Inferred query type (api_flow, implementation, data, entrypoint)
        """
        query_lower = query.lower()

        # API/Flow patterns
        api_keywords = [
            "api",
            "endpoint",
            "route",
            "request",
            "response",
            "handler",
            "flow",
            "from",
            "to",
        ]
        if any(kw in query_lower for kw in api_keywords):
            return "api_flow"

        # Data/Model patterns
        data_keywords = [
            "model",
            "schema",
            "database",
            "table",
            "entity",
            "store",
            "save",
            "load",
        ]
        if any(kw in query_lower for kw in data_keywords):
            return "data"

        # Entrypoint patterns
        entry_keywords = ["main", "start", "initialize", "setup", "entry", "config"]
        if any(kw in query_lower for kw in entry_keywords):
            return "entrypoint"

        # Default: implementation
        return "implementation"

    def explain(self, chunks: list[LayeredChunk], top_k: int = 10) -> str:
        """
        Generate explanation of layer-aware ordering.

        Args:
            chunks: Layered chunks
            top_k: Number of top chunks to explain

        Returns:
            Human-readable explanation
        """
        lines = ["Domain-Aware Context Ordering:"]
        lines.append(f"Total chunks: {len(chunks)}")
        lines.append(f"\nLayer Distribution: {self._get_layer_distribution(chunks)}")
        lines.append(f"\nTop {top_k} chunks:")

        for i, chunk in enumerate(chunks[:top_k], 1):
            lines.append(
                f"{i}. {chunk.chunk_id} (layer={chunk.layer.value}, "
                f"priority={chunk.layer_priority}, "
                f"orig={chunk.original_score:.3f}, "
                f"adj={chunk.adjusted_score:.3f})"
            )

        return "\n".join(lines)
