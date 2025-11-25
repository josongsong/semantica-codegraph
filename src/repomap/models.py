"""
RepoMap Data Models

Project structure map with importance metrics and summaries.

RepoMap provides a hierarchical view of the codebase with:
- Tree structure (repo → module → file → symbol)
- Importance metrics (PageRank, LOC, change frequency)
- LLM summaries for navigation
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class RepoMapMetrics(BaseModel):
    """
    Metrics for a RepoMap node.

    Metrics are computed from:
    - Code structure (LOC, symbol count)
    - Graph topology (PageRank, in/out degree)
    - Git history (change frequency)
    - Runtime data (hot score, error rate)
    """

    loc: int = 0
    """Lines of code (excluding comments/blanks)"""

    symbol_count: int = 0
    """Number of symbols (functions, classes, etc.)"""

    edge_degree: int = 0
    """Total in-degree + out-degree in code graph"""

    pagerank: float = 0.0
    """PageRank score (0.0 - 1.0)"""

    change_freq: float = 0.0
    """Git change frequency (commits per month)"""

    hot_score: float = 0.0
    """Runtime hotness score (0.0 - 1.0)"""

    error_score: float = 0.0
    """Error frequency score (0.0 - 1.0)"""

    importance: float = 0.0
    """Combined importance score (0.0 - 1.0)"""

    drift_score: float = 0.0
    """Span drift score from Chunk layer (0.0 - 1.0)"""


class RepoMapNode(BaseModel):
    """
    A node in the RepoMap tree.

    RepoMap extends Chunk hierarchy with:
    - Metrics (importance, PageRank, etc.)
    - Summaries (LLM-generated or rule-based)
    - Cross-references (chunks, graph nodes)

    ID format: repomap:{repo_id}:{snapshot_id}:{kind}:{path_or_fqn}
    """

    id: str
    """Unique node ID"""

    repo_id: str
    """Repository identifier"""

    snapshot_id: str
    """Snapshot/commit/branch identifier"""

    kind: Literal[
        "repo",
        "project",
        "module",
        "dir",
        "file",
        "class",
        "function",
        "symbol",
    ]
    """Node type in hierarchy"""

    name: str
    """Display name"""

    path: str | None = None
    """File/directory path (for file/dir nodes)"""

    fqn: str | None = None
    """Fully qualified name (for symbol nodes)"""

    parent_id: str | None = None
    """Parent node ID"""

    children_ids: list[str] = Field(default_factory=list)
    """Child node IDs"""

    depth: int = 0
    """Depth in tree (0 = repo root)"""

    # Cross-references
    chunk_ids: list[str] = Field(default_factory=list)
    """Related Chunk IDs"""

    graph_node_ids: list[str] = Field(default_factory=list)
    """Related GraphNode IDs"""

    # Metrics
    metrics: RepoMapMetrics = Field(default_factory=RepoMapMetrics)
    """Importance metrics"""

    # Summary
    summary_title: str | None = None
    """One-line summary (LLM or rule-based)"""

    summary_body: str | None = None
    """Detailed summary (2-3 sentences)"""

    summary_tags: list[str] = Field(default_factory=list)
    """Tags for categorization (e.g., ["indexing", "pipeline"])"""

    summary_text: str | None = None
    """Full text for vector index"""

    # Metadata
    language: str | None = None
    """Programming language (if applicable)"""

    is_entrypoint: bool = False
    """Is this an entrypoint (route, main, CLI)?"""

    is_test: bool = False
    """Is this a test file/function?"""

    attrs: dict[str, Any] = Field(default_factory=dict)
    """Additional attributes"""


class RepoMapSnapshot(BaseModel):
    """
    A complete RepoMap snapshot.

    Represents the project structure at a specific point in time.
    """

    repo_id: str
    """Repository identifier"""

    snapshot_id: str
    """Snapshot/commit/branch identifier"""

    root_node_id: str
    """Root RepoMap node ID"""

    nodes: list[RepoMapNode]
    """All nodes in the tree"""

    schema_version: str = "1.0"
    """RepoMap schema version"""

    created_at: str | None = None
    """ISO timestamp"""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Additional metadata"""

    def get_node(self, node_id: str) -> RepoMapNode | None:
        """Get node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_children(self, node_id: str) -> list[RepoMapNode]:
        """Get all children of a node."""
        node = self.get_node(node_id)
        if not node:
            return []
        return [self.get_node(child_id) for child_id in node.children_ids if self.get_node(child_id)]

    def get_subtree(self, node_id: str) -> list[RepoMapNode]:
        """Get node and all descendants."""
        node = self.get_node(node_id)
        if not node:
            return []

        result = [node]
        for child in self.get_children(node_id):
            result.extend(self.get_subtree(child.id))
        return result


class RepoMapBuildConfig(BaseModel):
    """
    Configuration for RepoMap building.
    """

    # Heuristic weights
    heuristic_loc_weight: float = 0.3
    """Weight for LOC in heuristic score"""

    heuristic_symbol_weight: float = 0.4
    """Weight for symbol count in heuristic score"""

    heuristic_edge_weight: float = 0.3
    """Weight for edge degree in heuristic score"""

    # PageRank settings (Phase 2)
    pagerank_enabled: bool = False
    """Enable PageRank computation"""

    pagerank_damping: float = 0.85
    """PageRank damping factor"""

    pagerank_max_iterations: int = 20
    """Maximum PageRank iterations"""

    # Summary settings (Phase 3)
    summary_enabled: bool = False
    """Enable LLM summaries"""

    summary_top_percent: float = 0.2
    """Summarize top N% of nodes"""

    summary_always_entrypoints: bool = True
    """Always summarize entrypoints"""

    # Filtering
    include_tests: bool = False
    """Include test files in RepoMap"""

    min_loc: int = 10
    """Minimum LOC to include file"""

    max_depth: int = 10
    """Maximum tree depth"""
