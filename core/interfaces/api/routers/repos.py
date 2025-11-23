"""Repositories API Router."""

from fastapi import APIRouter, Query

from ..dependencies import GraphServiceDep
from ..schemas.repo_schema import RepoMapResponse, RepoMapNodeSchema

router = APIRouter()


@router.get("/")
async def list_repositories():
    """List all repositories."""
    # TODO: Implement
    raise NotImplementedError


@router.get("/{repo_id}")
async def get_repository(repo_id: str):
    """Get repository details."""
    # TODO: Implement
    raise NotImplementedError


@router.get("/{repo_id}/repomap", response_model=RepoMapResponse)
async def get_repo_map(
    repo_id: str,
    token_budget: int = Query(
        default=8000,
        ge=1000,
        le=100000,
        description="Maximum token budget for the repository map"
    ),
    graph_service: GraphServiceDep = None,
):
    """
    Get repository map with importance scoring and token budget management.

    This endpoint generates a hierarchical view of the repository structure
    (Repository → Project → Module → File → Symbol) optimized for LLM context.

    The map is built considering:
    - Importance scores (PageRank + Git activity + Runtime stats)
    - Token estimates (skeleton code-based)
    - Token budget constraints

    Args:
        repo_id: Repository identifier
        token_budget: Maximum tokens for the map (default: 8000)
        graph_service: Graph service dependency

    Returns:
        Hierarchical repository map within token budget
    """
    # Build repo map using graph service
    root = await graph_service.build_repo_map(
        repo_id=repo_id,
        token_budget=token_budget
    )

    # Convert to response schema
    def convert_to_schema(node) -> RepoMapNodeSchema:
        return RepoMapNodeSchema(
            node_id=node.node_id,
            label=node.label,
            node_type=node.node_type,
            importance_score=node.importance_score,
            token_estimate=node.token_estimate,
            children=[convert_to_schema(child) for child in node.children]
        )

    root_schema = convert_to_schema(root)

    # Calculate total tokens and node count
    def count_tokens_and_nodes(node: RepoMapNodeSchema) -> tuple[int, int]:
        tokens = node.token_estimate
        nodes = 1
        for child in node.children:
            child_tokens, child_nodes = count_tokens_and_nodes(child)
            tokens += child_tokens
            nodes += child_nodes
        return tokens, nodes

    total_tokens, nodes_included = count_tokens_and_nodes(root_schema)

    return RepoMapResponse(
        repo_id=repo_id,
        root=root_schema,
        total_tokens=total_tokens,
        nodes_included=nodes_included
    )
