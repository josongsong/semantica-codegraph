"""
Context Value Objects

These models represent auxiliary context information that enriches code nodes
with temporal, security, runtime, and behavioral metadata.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CodeRange(BaseModel):
    """
    Line and byte range for code location.

    Supports both line-based (for display) and byte-offset (for LSP/compiler API).
    """

    start_line: int
    end_line: int
    start_byte: Optional[int] = None  # For LSP compatibility
    end_byte: Optional[int] = None  # For LSP compatibility


class GitContext(BaseModel):
    """
    Temporal and social signals (who, when, how often).
    Provides git history context for nodes.
    """

    last_modified_at: datetime
    last_modified_by: str
    commit_hash: str
    change_frequency: Literal["low", "medium", "high"]
    authors: list[str] = Field(default_factory=list)


class SecurityLevel(str, Enum):
    """Security access levels for enterprise ACL."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class SecurityContext(BaseModel):
    """Enterprise ACL context for access control."""

    access_level: SecurityLevel
    owner_team: str
    required_scopes: list[str] = Field(default_factory=list)


class RuntimeStats(BaseModel):
    """
    Runtime and operational signals.
    Tracks code health metrics like coverage and error rates.
    """

    test_coverage: float
    is_hotspot: bool
    recent_error_rate: float


class LexicalFeatures(BaseModel):
    """
    Lexical features for search and filtering.
    Extracted tokens and literals from code.
    """

    identifiers: list[str] = Field(default_factory=list)
    string_literals: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    special_tokens: list[str] = Field(default_factory=list)


class SemanticFeatures(BaseModel):
    """
    Semantic features for embedding.
    Natural language summary optimized for vector search.
    """

    embedding_text: str


class BehavioralTags(BaseModel):
    """
    Behavioral characteristic tags for agent reasoning.
    Helps LLM agents understand code behavior and side effects.
    """

    is_test: bool = False
    has_side_effect: bool = False
    is_generated: bool = False
    io_call: bool = False
    db_call: bool = False
    network_call: bool = False
    is_async: bool = False


class ErrorContext(BaseModel):
    """
    Error propagation path tracking.
    Tracks which exceptions are raised and handled.
    """

    raises: list[str] = Field(default_factory=list)
    handles: list[str] = Field(default_factory=list)
    fallback_behavior: Optional[str] = None


class Parameter(BaseModel):
    """Function or method parameter."""

    name: str
    type: str
