"""
Boundary Matching Domain Models (RFC-101 Phase 1)

Models for LLM-assisted boundary matching with graph-based pre-ranking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BoundaryType(Enum):
    """Type of boundary to match."""

    HTTP_ENDPOINT = "http_endpoint"
    GRPC_SERVICE = "grpc_service"
    MESSAGE_QUEUE = "message_queue"
    DATABASE_QUERY = "database_query"
    EXTERNAL_API = "external_api"


class HTTPMethod(Enum):
    """HTTP methods for endpoint matching."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class BoundarySpec:
    """
    Specification for finding a boundary in code.

    Used to describe what boundary to search for (e.g., HTTP endpoint, gRPC service).
    """

    # Boundary type
    boundary_type: BoundaryType

    # HTTP endpoint specific
    endpoint: Optional[str] = None  # "/api/users/{id}"
    http_method: Optional[HTTPMethod] = None  # GET, POST, etc.

    # gRPC specific
    service_name: Optional[str] = None  # "UserService"
    rpc_method: Optional[str] = None  # "GetUser"

    # Message queue specific
    topic: Optional[str] = None  # "user.created"
    queue_name: Optional[str] = None  # "user-events"

    # Database specific
    table_name: Optional[str] = None  # "users"
    operation: Optional[str] = None  # "SELECT", "INSERT"

    # External API specific
    api_host: Optional[str] = None  # "api.github.com"
    api_path: Optional[str] = None  # "/repos/{owner}/{repo}"

    # Search context
    file_pattern: Optional[str] = None  # "**/*.py" (glob pattern)
    module_pattern: Optional[str] = None  # "myapp.api.*"

    def __post_init__(self):
        """Validate boundary spec fields after initialization."""
        # HTTP endpoint validation (allow empty string for edge case testing)
        if self.boundary_type == BoundaryType.HTTP_ENDPOINT:
            if self.endpoint is None:
                raise ValueError("HTTP_ENDPOINT requires 'endpoint' field (cannot be None)")

        # gRPC service validation
        elif self.boundary_type == BoundaryType.GRPC_SERVICE:
            if not self.service_name:
                raise ValueError("GRPC_SERVICE requires 'service_name' field")

        # Message queue validation
        elif self.boundary_type == BoundaryType.MESSAGE_QUEUE:
            if not self.topic and not self.queue_name:
                raise ValueError("MESSAGE_QUEUE requires 'topic' or 'queue_name' field")

        # Database query validation
        elif self.boundary_type == BoundaryType.DATABASE_QUERY:
            if not self.table_name:
                raise ValueError("DATABASE_QUERY requires 'table_name' field")

        # External API validation
        elif self.boundary_type == BoundaryType.EXTERNAL_API:
            if not self.api_host:
                raise ValueError("EXTERNAL_API requires 'api_host' field")

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.boundary_type == BoundaryType.HTTP_ENDPOINT:
            return f"{self.http_method.value if self.http_method else '?'} {self.endpoint or '?'}"
        elif self.boundary_type == BoundaryType.GRPC_SERVICE:
            return f"{self.service_name or '?'}.{self.rpc_method or '?'}"
        elif self.boundary_type == BoundaryType.MESSAGE_QUEUE:
            return f"MQ: {self.topic or self.queue_name or '?'}"
        elif self.boundary_type == BoundaryType.DATABASE_QUERY:
            return f"DB: {self.operation or '?'} {self.table_name or '?'}"
        elif self.boundary_type == BoundaryType.EXTERNAL_API:
            return f"API: {self.api_host or '?'}{self.api_path or '?'}"
        return f"{self.boundary_type.value}"


@dataclass
class BoundaryCandidate:
    """
    A candidate match for a boundary spec.

    Includes scoring from different ranking stages.
    """

    # Node information
    node_id: str  # IR node ID
    file_path: str
    function_name: str
    line_number: int
    code_snippet: str  # First 200 chars

    # Pattern matching score (0.0-1.0)
    pattern_score: float = 0.0

    # Graph-based score (0.0-1.0)
    graph_score: float = 0.0

    # LLM ranking score (0.0-1.0)
    llm_score: float = 0.0

    # Rust verification result
    type_verified: bool = False
    verification_error: Optional[str] = None

    # Combined final score
    final_score: float = 0.0

    # Metadata
    decorator_name: Optional[str] = None  # "@app.get", "@router.post"
    http_path: Optional[str] = None  # Extracted from decorator
    distance_from_entry: Optional[int] = None  # Graph distance

    def compute_final_score(
        self, pattern_weight: float = 0.3, graph_weight: float = 0.4, llm_weight: float = 0.3
    ) -> float:
        """
        Compute weighted final score.

        Default weights:
        - Pattern: 0.3 (fast but limited)
        - Graph: 0.4 (structural, high signal)
        - LLM: 0.3 (semantic understanding)

        Raises:
            ValueError: If any weight is negative
        """
        # Validate weights are non-negative
        if pattern_weight < 0 or graph_weight < 0 or llm_weight < 0:
            raise ValueError(
                f"Weights must be non-negative. Got pattern={pattern_weight}, graph={graph_weight}, llm={llm_weight}"
            )

        self.final_score = (
            self.pattern_score * pattern_weight + self.graph_score * graph_weight + self.llm_score * llm_weight
        )
        return self.final_score

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"{self.function_name} ({self.file_path}:{self.line_number}) "
            f"[P:{self.pattern_score:.2f} G:{self.graph_score:.2f} "
            f"L:{self.llm_score:.2f} → {self.final_score:.2f}]"
        )


@dataclass
class BoundaryMatchResult:
    """
    Result of boundary matching operation.

    Includes best match and all candidates considered.
    """

    # Best match (if found)
    best_match: Optional[BoundaryCandidate] = None

    # All candidates considered (sorted by final score)
    candidates: list[BoundaryCandidate] = field(default_factory=list)

    # Search stats
    total_nodes_scanned: int = 0
    pattern_matches: int = 0
    graph_ranked: int = 0
    llm_ranked: int = 0

    # Performance metrics
    pattern_time_ms: float = 0.0
    graph_time_ms: float = 0.0
    llm_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Confidence
    confidence: float = 0.0  # 0.0-1.0

    # Decision metadata
    decision_path: list[str] = field(default_factory=list)  # ["fast_path", "graph_ranking"]

    @property
    def success(self) -> bool:
        """Whether match was successful."""
        return self.best_match is not None and self.confidence >= 0.85

    def add_decision(self, decision: str):
        """Add decision to path for debugging."""
        self.decision_path.append(decision)

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.best_match:
            return (
                f"✓ Found: {self.best_match.function_name} "
                f"(confidence: {self.confidence:.2%}, "
                f"time: {self.total_time_ms:.1f}ms)"
            )
        return f"✗ No match (scanned {self.total_nodes_scanned} nodes, time: {self.total_time_ms:.1f}ms)"
