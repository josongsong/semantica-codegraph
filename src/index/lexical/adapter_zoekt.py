"""
Zoekt-based Lexical Index Adapter

Implements LexicalIndexPort using Zoekt for file-based text search.

Architecture:
    Zoekt (file search) → ChunkStore (file+line → Chunk) → SearchHit (chunk_id)

Mapping Strategy:
    1. Zoekt returns (file_path, line_number)
    2. ChunkStore.find_chunk_by_file_and_line maps to Chunk
    3. Fallback: function > class > file > virtual chunk_id
"""

import logging
import subprocess
from pathlib import Path
from typing import Any

from src.foundation.chunk.store import ChunkStore
from src.index.common.documents import SearchHit
from src.infra.search.zoekt import ZoektAdapter

logger = logging.getLogger(__name__)


class RepoPathResolver:
    """
    Resolves repo_id ↔ filesystem path ↔ Zoekt repo name.

    For MVP, uses simple directory mapping.
    """

    def __init__(self, repos_root: str = "./repos"):
        self.repos_root = Path(repos_root)

    def get_fs_path(self, repo_id: str) -> Path:
        """Get filesystem path for repo_id"""
        return self.repos_root / repo_id

    def get_zoekt_repo_name(self, repo_id: str) -> str:
        """Get Zoekt repo name (same as repo_id for MVP)"""
        return repo_id


class ZoektLexicalIndex:
    """
    Lexical search implementation using Zoekt.

    Hybrid approach:
    - Zoekt provides fast file-based search
    - ChunkStore maps file+line to semantic chunks
    - Fallback to virtual chunk_id if mapping fails

    Usage:
        lexical = ZoektLexicalIndex(
            zoekt_adapter=ZoektAdapter("localhost", 7205),
            chunk_store=chunk_store,
            repo_resolver=RepoPathResolver(),
        )

        hits = await lexical.search("myrepo", "commit123", "HybridRetriever", limit=50)
    """

    def __init__(
        self,
        zoekt_adapter: ZoektAdapter,
        chunk_store: ChunkStore,
        repo_resolver: RepoPathResolver | None = None,
        zoekt_index_cmd: str = "zoekt-index",
    ):
        self.zoekt = zoekt_adapter
        self.chunk_store = chunk_store
        self.repo_resolver = repo_resolver or RepoPathResolver()
        self.zoekt_index_cmd = zoekt_index_cmd

    # ============================================================
    # LexicalIndexPort Implementation
    # ============================================================

    async def reindex_repo(self, repo_id: str, snapshot_id: str) -> None:
        """
        Full repository reindex with Zoekt.

        Runs: zoekt-index -index {zoekt_repo} {repo_path}

        Args:
            repo_id: Repository identifier
            snapshot_id: Git commit hash (currently unused in MVP)
        """
        repo_path = self.repo_resolver.get_fs_path(repo_id)
        zoekt_repo = self.repo_resolver.get_zoekt_repo_name(repo_id)

        if not repo_path.exists():
            logger.error(f"Repository path not found: {repo_path}")
            raise FileNotFoundError(f"Repository not found: {repo_id}")

        try:
            # Run zoekt-index command
            cmd = [
                self.zoekt_index_cmd,
                "-index",
                zoekt_repo,
                str(repo_path),
            ]
            logger.info(f"Running Zoekt index: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Zoekt index completed: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Zoekt index failed: {e.stderr}")
            raise RuntimeError(f"Zoekt indexing failed for {repo_id}") from e

    async def reindex_paths(self, repo_id: str, snapshot_id: str, paths: list[str]) -> None:
        """
        Partial reindex for specific files (MVP: falls back to full reindex).

        TODO Phase 2: Implement delta indexing with Zoekt incremental options.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            paths: List of file paths to reindex
        """
        logger.warning(f"reindex_paths not implemented for {repo_id}, falling back to full reindex")
        await self.reindex_repo(repo_id, snapshot_id)

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Lexical search with Zoekt → Chunk mapping.

        Mapping strategy:
        1. Exact function/class chunk (priority 1) → score 1.0
        2. File chunk (priority 2) → score 0.8
        3. Virtual chunk_id (priority 3) → score 0.5 + warning

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (currently unused, assumes latest)
            query: Search query (text/regex/identifier)
            limit: Maximum results

        Returns:
            List of SearchHit with source="lexical"
        """
        # Build Zoekt query with repo filter
        zoekt_query = self._build_zoekt_query(query, repo=repo_id)

        # Execute Zoekt search
        try:
            file_matches = await self.zoekt.search(
                query=zoekt_query, limit=limit * 3  # Request more for mapping fallback
            )
        except Exception as e:
            logger.error(f"Zoekt search failed: {e}")
            return []

        # Convert Zoekt results to SearchHits
        hits: list[SearchHit] = []
        mapping_stats = {"exact": 0, "file_fallback": 0, "virtual": 0}

        for file_match in file_matches:
            if not file_match.Matches:
                continue

            for match in file_match.Matches:
                hit = await self._map_zoekt_match_to_search_hit(
                    repo_id=repo_id,
                    file_path=file_match.FileName,
                    line=match.LineNum,
                    context=self._extract_context(match),
                    score=1.0,  # Base score from Zoekt
                    stats=mapping_stats,
                )
                if hit:
                    hits.append(hit)

        # Sort by score (exact matches first)
        hits.sort(key=lambda h: h.score, reverse=True)

        # Log mapping stats
        logger.info(
            f"Zoekt→Chunk mapping: exact={mapping_stats['exact']}, "
            f"file={mapping_stats['file_fallback']}, "
            f"virtual={mapping_stats['virtual']}"
        )

        return hits[:limit]

    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete Zoekt index for repository.

        TODO: Implement Zoekt index deletion.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
        """
        logger.warning(f"delete_repo not implemented for {repo_id}")

    # ============================================================
    # Private Helpers
    # ============================================================

    def _build_zoekt_query(
        self,
        user_query: str,
        repo: str | None = None,
        language: str | None = None,
        file_prefix: str | None = None,
    ) -> str:
        """
        Build Zoekt DSL query.

        Args:
            user_query: User search query
            repo: Repository filter (e.g., "myrepo")
            language: Language filter (e.g., "python")
            file_prefix: File path prefix (e.g., "src/core/")

        Returns:
            Zoekt query string

        Examples:
            _build_zoekt_query("HybridRetriever", repo="myrepo")
            → "repo:myrepo HybridRetriever"

            _build_zoekt_query("def.*search", language="python")
            → "lang:python def.*search"
        """
        parts: list[str] = []

        if repo:
            parts.append(f"repo:{repo}")
        if language:
            parts.append(f"lang:{language}")
        if file_prefix:
            parts.append(f"file:{file_prefix}/*")

        parts.append(user_query)
        return " ".join(parts)

    async def _map_zoekt_match_to_search_hit(
        self,
        repo_id: str,
        file_path: str,
        line: int,
        context: str,
        score: float,
        stats: dict[str, int],
    ) -> SearchHit | None:
        """
        Map Zoekt match (file+line) to SearchHit.

        Mapping priority:
        1. Exact function/class chunk → score 1.0
        2. File chunk fallback → score 0.8
        3. Virtual chunk_id → score 0.5

        Args:
            repo_id: Repository ID
            file_path: File path from Zoekt
            line: Line number from Zoekt
            context: Code preview
            score: Base score from Zoekt
            stats: Mapping statistics (updated in-place)

        Returns:
            SearchHit or None if skip
        """
        # Try exact chunk mapping (function > class > file)
        chunk = await self._get_chunk_async(repo_id, file_path, line)

        if chunk:
            # Exact mapping
            stats["exact"] += 1
            return SearchHit(
                chunk_id=chunk.chunk_id,
                file_path=file_path,
                symbol_id=chunk.symbol_id,
                score=score,
                source="lexical",
                metadata={
                    "line": line,
                    "preview": context,
                    "kind": chunk.kind,
                    "mapped": True,
                    "match_type": "exact",
                },
            )

        # Fallback: File chunk
        file_chunk = await self._get_file_chunk_async(repo_id, file_path)
        if file_chunk:
            stats["file_fallback"] += 1
            return SearchHit(
                chunk_id=file_chunk.chunk_id,
                file_path=file_path,
                symbol_id=file_chunk.symbol_id,
                score=score * 0.8,  # Penalize file-level mapping
                source="lexical",
                metadata={
                    "line": line,
                    "preview": context,
                    "kind": "file",
                    "mapped": True,
                    "match_type": "file_fallback",
                },
            )

        # Fallback: Virtual chunk_id
        stats["virtual"] += 1
        return SearchHit(
            chunk_id=f"virtual:{repo_id}:{file_path}:{line}",
            file_path=file_path,
            symbol_id=None,
            score=score * 0.5,  # Heavy penalty for virtual mapping
            source="lexical",
            metadata={
                "line": line,
                "preview": context,
                "kind": "virtual",
                "mapped": False,
                "match_type": "virtual",
                "warning": "chunk_mapping_failed",
            },
        )

    async def _get_chunk_async(self, repo_id: str, file_path: str, line: int) -> Any | None:
        """
        Async wrapper for ChunkStore.find_chunk_by_file_and_line.

        TODO: Make ChunkStore async-native in Phase 2.
        """
        try:
            # For async stores (PostgresChunkStore)
            if callable(self.chunk_store.find_chunk_by_file_and_line):
                result = self.chunk_store.find_chunk_by_file_and_line(
                    repo_id=repo_id,
                    file_path=file_path,
                    line=line,
                )
                # If it's a coroutine, await it
                if hasattr(result, "__await__"):
                    return await result
                return result
        except Exception as e:
            logger.debug(f"Chunk mapping failed for {file_path}:{line}: {e}")
            return None

    async def _get_file_chunk_async(self, repo_id: str, file_path: str) -> Any | None:
        """Async wrapper for ChunkStore.find_file_chunk"""
        try:
            result = self.chunk_store.find_file_chunk(
                repo_id=repo_id,
                file_path=file_path,
            )
            if hasattr(result, "__await__"):
                return await result
            return result
        except Exception as e:
            logger.debug(f"File chunk mapping failed for {file_path}: {e}")
            return None

    def _extract_context(self, match: Any) -> str:
        """
        Extract code preview from Zoekt match.

        Args:
            match: ZoektMatch with Fragments

        Returns:
            Concatenated code preview
        """
        if not hasattr(match, "Fragments"):
            return ""

        parts = []
        for frag in match.Fragments:
            parts.append(frag.Pre + frag.Match + frag.Post)

        return "".join(parts).strip()
