"""
Domain Nodes: Git Workflow and Logical Structure

This module contains all node types for the codegraph system:
- Git Workflow: Repository, Branch, Commit, PullRequest, Tag
- Logical Structure: Project, Module, File, Symbol
"""

from __future__ import annotations

from typing import List, Optional, Literal
from enum import Enum
from datetime import datetime

from pydantic import Field

from .graph import BaseSemanticaNode
from .context import GitContext, SecurityContext, RuntimeStats, Parameter


# ==============================================================================
# Git Workflow Nodes
# ==============================================================================

class RepositoryNode(BaseSemanticaNode):
    """Level 0: Repository Root"""
    node_type: Literal["repository"] = "repository"
    repo_name: str
    remote_url: str
    default_branch: str = "main"
    monorepo_layout: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None


class BranchNode(BaseSemanticaNode):
    """Git Branch (Logical View)"""
    node_type: Literal["branch"] = "branch"
    repo_id: str
    name: str
    head_commit: str
    is_default: bool = False


class CommitNode(BaseSemanticaNode):
    """Git Commit History"""
    node_type: Literal["commit"] = "commit"
    repo_id: str
    hash: str
    author: str
    author_email: Optional[str] = None
    authored_at: datetime
    message: str
    parents: List[str] = Field(default_factory=list)


class PullRequestState(str, Enum):
    """Pull request lifecycle states."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


class PullRequestNode(BaseSemanticaNode):
    """Code Review Context"""
    node_type: Literal["pull_request"] = "pull_request"
    repo_id: str
    pr_number: int
    title: str
    state: PullRequestState
    source_branch: str
    target_branch: str
    created_at: datetime
    merged_at: Optional[datetime] = None
    author: Optional[str] = None
    url: Optional[str] = None


class TagNode(BaseSemanticaNode):
    """Release / Git Tag"""
    node_type: Literal["tag"] = "tag"
    repo_id: str
    name: str
    commit_hash: str
    created_at: Optional[datetime] = None
    message: Optional[str] = None


from pydantic import BaseModel

class BranchChunkMapping(BaseModel):
    """
    [Deduplication Layer]
    Maps which chunks each branch references (prevents duplicate storage).
    """
    repo_id: str
    branch_name: str
    commit_hash: str
    chunk_id: str      # References CanonicalLeafChunk.node_id


# ==============================================================================
# Logical Structure Nodes
# ==============================================================================

class ProjectType(str, Enum):
    """Project classification types."""
    APPLICATION = "application"
    LIBRARY = "library"
    TOOL = "tool"
    SERVICE = "service"


class ProjectNode(BaseSemanticaNode):
    """Level 1: Project (Workspace/Build Unit)"""
    node_type: Literal["project"] = "project"
    repo_id: str
    name: str
    root_path: str
    project_type: ProjectType
    language: str
    framework: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None


class ModuleNode(BaseSemanticaNode):
    """Level 2: Module (Architectural Group)"""
    node_type: Literal["module"] = "module"
    project_id: str
    name: str
    path: str
    role: Optional[str] = None
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None


class FileCategory(str, Enum):
    """File classification categories."""
    SOURCE = "source"
    CONFIG = "config"
    DOC = "doc"
    TEST = "test"
    OTHER = "other"


class FileNode(BaseSemanticaNode):
    """Level 3: Physical File (Parsing Strategy Anchor)"""
    node_type: Literal["file"] = "file"
    project_id: str
    module_id: Optional[str] = None
    file_path: str
    language: str
    extension: str
    category: FileCategory = FileCategory.SOURCE
    loc: Optional[int] = None
    skeleton_code: Optional[str] = None
    summary: Optional[str] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None


class SymbolKind(str, Enum):
    """Symbol types in code."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    VARIABLE = "variable"
    CONSTANT = "constant"
    ROUTE = "route"
    CONFIG_KEY = "config_key"
    MARKDOWN_HEADER = "markdown_header"


class Visibility(str, Enum):
    """Symbol visibility levels."""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


class SymbolNode(BaseSemanticaNode):
    """Level 4: Symbol (Logical Unit / Agent Tool)"""
    node_type: Literal["symbol"] = "symbol"
    file_id: str
    file_path: str
    symbol_name: str
    kind: SymbolKind
    signature: Optional[str] = None
    visibility: Visibility = Visibility.PUBLIC
    parameters: List[Parameter] = Field(default_factory=list)
    return_type: Optional[str] = None
    skeleton_code: Optional[str] = None
    summary: Optional[str] = None
    runtime_stats: Optional[RuntimeStats] = None
    git_context: Optional[GitContext] = None
    security_context: Optional[SecurityContext] = None
