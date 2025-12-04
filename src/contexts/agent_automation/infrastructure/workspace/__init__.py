"""Workspace Management System.

Provides isolated workspace sessions using git worktree
for parallel agent execution and safe experimentation.
"""

from .manager import WorkspaceManager
from .session import WorkspaceSession
from .worktree import GitWorktreeAdapter

__all__ = [
    "WorkspaceManager",
    "WorkspaceSession",
    "GitWorktreeAdapter",
]
