"""
FastAPI Dependencies

Dependency injection for FastAPI endpoints.
Provides access to services and ports.
"""

from typing import Annotated

from fastapi import Depends

from ...core.services import (
    GitService,
    GraphService,
    IndexingService,
    SearchService,
)

# TODO: Import container and wire dependencies
# These are placeholders - actual implementation will use the DI container


def get_indexing_service() -> IndexingService:
    """Get indexing service instance."""
    # TODO: Get from container
    raise NotImplementedError


def get_search_service() -> SearchService:
    """Get search service instance."""
    # TODO: Get from container
    raise NotImplementedError


def get_graph_service() -> GraphService:
    """Get graph service instance."""
    # TODO: Get from container
    raise NotImplementedError


def get_git_service() -> GitService:
    """Get git service instance."""
    # TODO: Get from container
    raise NotImplementedError


# Type aliases for dependency injection
IndexingServiceDep = Annotated[IndexingService, Depends(get_indexing_service)]
SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
GitServiceDep = Annotated[GitService, Depends(get_git_service)]
