"""
Relational Store Port

Abstract interface for relational database operations.
Implementations: PostgreSQL (SQLAlchemy), SQLite, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from ..domain.nodes import (
    RepositoryNode,
    ProjectNode,
    FileNode,
    SymbolNode,
)
from ..domain.chunks import CanonicalLeafChunk


class RelationalStorePort(ABC):
    """
    Port for relational database operations.

    Responsibilities:
    - Store structured metadata
    - Query by filters and joins
    - Manage CRUD operations
    """

    # Repository Operations
    @abstractmethod
    async def create_repository(self, repo: RepositoryNode) -> None:
        """Create a repository record."""
        pass

    @abstractmethod
    async def get_repository(self, repo_id: str) -> Optional[RepositoryNode]:
        """Retrieve a repository by ID."""
        pass

    @abstractmethod
    async def list_repositories(self) -> List[RepositoryNode]:
        """List all repositories."""
        pass

    # Project Operations
    @abstractmethod
    async def create_project(self, project: ProjectNode) -> None:
        """Create a project record."""
        pass

    @abstractmethod
    async def get_projects_by_repo(self, repo_id: str) -> List[ProjectNode]:
        """Get all projects in a repository."""
        pass

    # File Operations
    @abstractmethod
    async def create_file(self, file: FileNode) -> None:
        """Create a file record."""
        pass

    @abstractmethod
    async def get_files_by_project(self, project_id: str) -> List[FileNode]:
        """Get all files in a project."""
        pass

    @abstractmethod
    async def get_file(self, file_id: str) -> Optional[FileNode]:
        """Retrieve a file by ID."""
        pass

    # Symbol Operations
    @abstractmethod
    async def create_symbol(self, symbol: SymbolNode) -> None:
        """Create a symbol record."""
        pass

    @abstractmethod
    async def get_symbols_by_file(self, file_id: str) -> List[SymbolNode]:
        """Get all symbols in a file."""
        pass

    @abstractmethod
    async def search_symbols(
        self,
        query: str,
        repo_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[SymbolNode]:
        """Search symbols by name."""
        pass

    # Chunk Operations
    @abstractmethod
    async def create_chunk(self, chunk: CanonicalLeafChunk) -> None:
        """Create a chunk record."""
        pass

    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> Optional[CanonicalLeafChunk]:
        """Retrieve a chunk by ID."""
        pass

    @abstractmethod
    async def get_chunks_by_file(self, file_id: str) -> List[CanonicalLeafChunk]:
        """Get all chunks in a file."""
        pass

    @abstractmethod
    async def find_chunk_by_hash(self, content_hash: str) -> Optional[CanonicalLeafChunk]:
        """Find chunk by content hash (for deduplication)."""
        pass

    # Bulk Operations
    @abstractmethod
    async def bulk_create(self, entities: List[Any]) -> None:
        """Bulk create multiple entities."""
        pass

    @abstractmethod
    async def delete_by_repo(self, repo_id: str) -> None:
        """Delete all data for a repository."""
        pass
