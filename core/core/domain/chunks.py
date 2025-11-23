"""
Canonical Leaf Chunks and Vector Payloads

This module defines the core execution units (chunks) and their flattened
vector database representations. The mapper function converts rich tree
structures into flat storage payloads.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

from pydantic import BaseModel, Field

from .graph import BaseSemanticaNode, RelationshipType
from .context import (
    CodeRange,
    LexicalFeatures,
    SemanticFeatures,
    BehavioralTags,
    ErrorContext,
    GitContext,
    SecurityContext,
)


class CanonicalLeafChunk(BaseSemanticaNode):
    """
    Level 5: Leaf Chunk (Engine Internal Rich Representation)

    This is the atomic execution unit in the codegraph. Each chunk represents
    a semantically meaningful piece of code with all its context preserved.

    - content_hash: Ensures deduplication across branches
    - canonical_commit: Tracks the origin commit of this chunk
    """
    node_type: Literal["leaf_chunk"] = "leaf_chunk"

    # Hierarchy Links
    parent_symbol_id: Optional[str] = None
    repo_id: str
    project_id: str
    file_id: str
    file_path: str

    # Location & Content
    language: str
    code_range: CodeRange
    content_hash: str           # Hash of raw_code (Deduplication Key)
    canonical_commit: str       # Origin commit of this chunk

    raw_code: Optional[str] = None

    # Features
    lexical_features: Optional[LexicalFeatures] = None
    semantic_features: SemanticFeatures

    # Contexts
    behavioral_tags: BehavioralTags = Field(default_factory=BehavioralTags)
    error_context: ErrorContext = Field(default_factory=ErrorContext)
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None

    minimal_summary: Optional[str] = None


class VectorChunkPayload(BaseModel):
    """
    Vector DB Storage Payload (Flat Document)

    The vector database doesn't understand tree structures, so all parent
    context is denormalized and flattened into this payload. This enables
    join-free ultra-fast queries.

    Following the "Logical Tree, Physical Flat" principle from the manifesto.
    """
    id: str  # Chunk ID
    repo_id: str
    project_id: str
    file_id: str
    file_path: str
    uri: str
    language: str

    content: Optional[str]
    summary: Optional[str]
    embedding_source: str

    # Flattened Meta
    tags: Dict[str, bool]
    identifiers: List[str] = []

    # Flattened Graph Relations (promoted from relationships for fast access)
    rel_calls: List[str] = []
    rel_tests: List[str] = []
    rel_touches: List[str] = []  # PR/Commit connections
    rel_documents: List[str] = []

    # Contexts
    last_modified_at: Optional[datetime] = None
    change_frequency: Optional[str] = None
    content_hash: Optional[str] = None

    # Safety Net (everything else goes here)
    extra: Dict[str, Any] = {}


def canonical_leaf_to_vector_payload(chunk: CanonicalLeafChunk) -> VectorChunkPayload:
    """
    Mapper Function: Tree(Rich) -> Flat(Persistence)

    This function implements the critical "denormalization" step that flattens
    the rich tree structure into a flat payload for vector storage.

    Key operations:
    1. Flatten behavioral tags into a dict
    2. Promote key relationships to top-level fields
    3. Backup unknown relationships to extra dict
    4. Extract temporal info from git context
    5. Preserve all attrs in extra dict
    """
    uri = f"{chunk.file_path}#L{chunk.code_range.start_line}-L{chunk.code_range.end_line}"

    # 1. Flatten Tags
    tags = chunk.behavioral_tags.model_dump()

    # 2. Flatten Relationships (promote main relations + backup the rest)
    rel_calls = []
    rel_tests = []
    rel_touches = []
    rel_documents = []
    extra_rels = {}

    for rel in chunk.relationships:
        if rel.type == RelationshipType.CALLS:
            rel_calls.append(rel.target_id)
        elif rel.type == RelationshipType.TESTS:
            rel_tests.append(rel.target_id)
        elif rel.type == RelationshipType.TOUCHES:
            rel_touches.append(rel.target_id)
        elif rel.type == RelationshipType.DOCUMENTS:
            rel_documents.append(rel.target_id)
        else:
            # Unknown relationships auto-backup to extra
            key = f"rel_{rel.type.value}"
            if key not in extra_rels:
                extra_rels[key] = []
            extra_rels[key].append(rel.target_id)

    # 3. Extract Temporal Info
    modified_at = chunk.git_context.last_modified_at if chunk.git_context else None
    freq = chunk.git_context.change_frequency if chunk.git_context else None

    # 4. Construct Payload
    payload = VectorChunkPayload(
        id=chunk.node_id,
        repo_id=chunk.repo_id,
        project_id=chunk.project_id,
        file_id=chunk.file_id,
        file_path=chunk.file_path,
        uri=uri,
        language=chunk.language,
        content=chunk.raw_code,
        summary=chunk.minimal_summary or chunk.semantic_features.embedding_text,
        embedding_source=chunk.semantic_features.embedding_text,
        tags=tags,
        identifiers=chunk.lexical_features.identifiers if chunk.lexical_features else [],
        rel_calls=rel_calls,
        rel_tests=rel_tests,
        rel_touches=rel_touches,
        rel_documents=rel_documents,
        last_modified_at=modified_at,
        change_frequency=freq,
        content_hash=chunk.content_hash,
        # Merge attrs and extra_rels into extra (the safety net)
        extra={**chunk.attrs, **extra_rels}
    )

    return payload
