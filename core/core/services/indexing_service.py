"""
Indexing Service

Orchestrates repository and branch indexing pipeline.
Coordinates parsing, chunking, and storage across all ports.
"""

from typing import List, Optional
from pathlib import Path

from ..domain.nodes import RepositoryNode, ProjectNode, FileNode, SymbolNode
from ..domain.chunks import CanonicalLeafChunk, canonical_leaf_to_vector_payload
from ..ports.vector_store import VectorStorePort
from ..ports.graph_store import GraphStorePort
from ..ports.relational_store import RelationalStorePort
from ..ports.git_provider import GitProviderPort
from ..ports.llm_provider import LLMProviderPort
from ..ports.lexical_search_port import LexicalSearchPort
from .ingestion.parser import CodeParser
from .ingestion.chunker import CodeChunker


class IndexingService:
    """
    Repository indexing orchestrator.

    Implements the full indexing pipeline:
    1. Parse repository structure
    2. Extract symbols and chunks
    3. Generate embeddings
    4. Store in vector, graph, and relational stores
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        graph_store: GraphStorePort,
        relational_store: RelationalStorePort,
        git_provider: GitProviderPort,
        llm_provider: LLMProviderPort,
        lexical_search: LexicalSearchPort,
    ):
        """Initialize indexing service with all required ports."""
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.relational_store = relational_store
        self.git_provider = git_provider
        self.llm_provider = llm_provider
        self.lexical_search = lexical_search

        self.parser = CodeParser()
        self.chunker = CodeChunker(llm_provider)

    async def index_repository(
        self,
        repo_path: Path,
        branch: Optional[str] = None,
    ) -> RepositoryNode:
        """
        Index an entire repository.

        Args:
            repo_path: Path to repository
            branch: Branch to index (defaults to current branch)

        Returns:
            Indexed repository node
        """
        # TODO: Implement repository indexing
        raise NotImplementedError

    async def index_project(
        self,
        repo_id: str,
        project_path: Path,
    ) -> ProjectNode:
        """
        Index a project within a repository.

        Args:
            repo_id: Parent repository ID
            project_path: Path to project

        Returns:
            Indexed project node
        """
        # TODO: Implement project indexing
        raise NotImplementedError

    async def index_file(
        self,
        project_id: str,
        file_path: Path,
        language: str,
    ) -> tuple[FileNode, List[SymbolNode], List[CanonicalLeafChunk]]:
        """
        Index a single file.

        Args:
            project_id: Parent project ID
            file_path: Path to file
            language: Programming language

        Returns:
            Tuple of (file, symbols, chunks)
        """
        # TODO: Implement file indexing
        raise NotImplementedError

    async def store_chunks(
        self,
        chunks: List[CanonicalLeafChunk],
        collection_name: str = "codegraph",
    ) -> None:
        """
        Store chunks in vector and relational stores.

        Args:
            chunks: Chunks to store
            collection_name: Vector collection name
        """
        # Generate payloads
        payloads = [canonical_leaf_to_vector_payload(c) for c in chunks]

        # Generate embeddings
        embedding_texts = [p.embedding_source for p in payloads]
        vectors = await self.llm_provider.embed_texts(embedding_texts)

        # Store in vector DB
        await self.vector_store.upsert_chunks(collection_name, payloads, vectors)

        # Store metadata in relational DB
        await self.relational_store.bulk_create(chunks)

    async def reindex_repository(self, repo_id: str) -> None:
        """
        Reindex an entire repository (delete old data first).

        Args:
            repo_id: Repository ID
        """
        # Delete old data
        await self.relational_store.delete_by_repo(repo_id)
        await self.vector_store.delete_by_filter(
            "codegraph",
            {"repo_id": repo_id}
        )

        # TODO: Reindex
        raise NotImplementedError
