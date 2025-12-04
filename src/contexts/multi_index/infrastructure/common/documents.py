"""
Index Layer Common Schemas

IndexDocument: Unified document schema for Vector/Domain/Runtime indexes
SearchHit: Unified search result schema for all index types

DEPRECATED: These types have been moved to src.ports to avoid circular dependencies.
This module now re-exports them for backward compatibility.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Import base types from ports (to avoid circular dependency)


class IndexDocument(BaseModel):
    """
    Unified document schema for all indexes (Vector/Domain/Runtime).

    Lexical index (Zoekt) uses raw source files directly,
    so it doesn't consume IndexDocument.

    IndexDocument = Chunk + metadata + RepoMap scores + identifiers
    """

    # Identity
    id: str
    """Document ID (usually chunk_id for stable reference)"""

    chunk_id: str
    """Source Chunk ID"""

    repo_id: str
    """Repository identifier"""

    snapshot_id: str
    """Snapshot/commit/branch identifier (important for index consistency)"""

    file_path: str
    """File path"""

    language: str
    """Programming language"""

    # Symbol information
    symbol_id: str | None = None
    """Symbol ID from IR layer"""

    symbol_name: str | None = None
    """Symbol name (function/class name)"""

    # Search content (for Vector/Domain indexes)
    content: str
    """Full search text: [SUMMARY] + [SIGNATURE] + [CODE] + [META]"""

    identifiers: list[str] = Field(default_factory=list)
    """Identifier list: function names, class names, parameters, imports"""

    tags: dict[str, str] = Field(default_factory=dict)
    """
    Metadata tags for filtering/ranking:
    - kind: chunk kind (file/class/function)
    - module: module path
    - visibility: public/private
    - repomap_score: importance score from RepoMap (0.0-1.0)
    - parent_chunk_id: parent chunk ID for hierarchy
    - is_entrypoint: "true"/"false"
    - is_test: "true"/"false"
    """

    # Location
    start_line: int | None = None
    """Start line number"""

    end_line: int | None = None
    """End line number"""

    # Metadata
    created_at: str | None = None
    """ISO timestamp of document creation"""

    attrs: dict[str, Any] = Field(default_factory=dict)
    """Additional attributes"""


class SearchHit(BaseModel):
    """
    Unified search result schema for all index types.

    All indexes (Lexical/Vector/Symbol/Fuzzy/Domain/Runtime) return SearchHit.
    Retriever layer can fuse results using common schema.
    """

    chunk_id: str
    """Matched Chunk ID"""

    file_path: str | None
    """File path"""

    symbol_id: str | None = None
    """Symbol ID (if matched symbol)"""

    score: float
    """Search score (0.0 - 1.0, higher = better)"""

    source: Literal["lexical", "vector", "symbol", "fuzzy", "domain", "runtime", "fused"]
    """Index source that produced this hit"""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """
    Additional metadata:
    - line: line number (for lexical)
    - preview: matched text preview (for lexical)
    - kind: chunk kind
    - matched: whether chunk mapping succeeded
    - distance: vector distance (for vector)
    - edge_type: matched edge type (for symbol)
    """
