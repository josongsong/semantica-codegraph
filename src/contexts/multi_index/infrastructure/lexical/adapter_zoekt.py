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

import subprocess
from pathlib import Path
from typing import Any

from src.contexts.code_foundation.infrastructure.chunk.store import ChunkStore
from src.contexts.multi_index.infrastructure.common.documents import SearchHit
from src.infra.observability import get_logger
from src.infra.search.zoekt import ZoektAdapter

logger = get_logger(__name__)


class RepoPathResolver:
    """
    Resolves repo_id ↔ filesystem path ↔ Zoekt repo name.

    For MVP, uses simple directory mapping.
    Supports custom path mappings for special cases (e.g., benchmarks).
    """

    def __init__(self, repos_root: str = "./repos", custom_mappings: dict[str, str] | None = None):
        """
        Initialize repo path resolver.

        Args:
            repos_root: Root directory for repositories (default: ./repos)
            custom_mappings: Optional dict mapping repo_id → custom filesystem path
                          Example: {"codegraph": "."} for benchmarking current directory
        """
        self.repos_root = Path(repos_root)
        self.custom_mappings = custom_mappings or {}

    def get_fs_path(self, repo_id: str) -> Path:
        """
        Get filesystem path for repo_id.

        Args:
            repo_id: Repository identifier

        Returns:
            Path to repository filesystem location
        """
        # Check custom mapping first
        if repo_id in self.custom_mappings:
            return Path(self.custom_mappings[repo_id])

        # Default: repos_root / repo_id
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
        zoekt_index_dir: str = "./data/zoekt-index",
    ):
        self.zoekt = zoekt_adapter
        self.chunk_store = chunk_store
        self.repo_resolver = repo_resolver or RepoPathResolver()
        self.zoekt_index_cmd = zoekt_index_cmd
        self.zoekt_index_dir = zoekt_index_dir
        self._ignore_dirs = [".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"]

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

        if not repo_path.exists():
            logger.error("zoekt_repo_path_not_found", repo_path=str(repo_path), repo_id=repo_id)
            raise FileNotFoundError(f"Repository not found: {repo_id}")

        try:
            import asyncio
            import os
            import shutil

            # Strategy 1: Inside Docker container (e.g., api-server container)
            if os.path.exists("/data/index"):
                # zoekt-indexserver handles indexing automatically
                logger.info(
                    "zoekt_docker_env_detected",
                    repo_id=repo_id,
                    message="Docker environment detected. Zoekt indexing handled by zoekt-indexserver.",
                )
                return

            # Strategy 2: Local with zoekt-index binary available
            if shutil.which(self.zoekt_index_cmd):
                # Ensure index directory exists
                index_dir = Path(self.zoekt_index_dir)
                index_dir.mkdir(parents=True, exist_ok=True)

                cmd = [
                    self.zoekt_index_cmd,
                    "-index",
                    str(index_dir),
                    "-ignore_dirs",
                    ",".join(self._ignore_dirs),
                    str(repo_path),
                ]
                logger.info("zoekt_index_starting", repo_id=repo_id, command=" ".join(cmd))
                # Use asyncio subprocess for non-blocking execution
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                result_stdout = stdout.decode() if stdout else ""
                result_stderr = stderr.decode() if stderr else ""
                returncode = proc.returncode

                # Zoekt sometimes returns non-zero even on success
                # Check for success indicators in output
                stderr_lower = result_stderr.lower()
                is_success = returncode == 0 or "finished shard" in stderr_lower or "files processed" in stderr_lower

                if is_success:
                    logger.info(
                        "zoekt_index_completed",
                        repo_id=repo_id,
                        returncode=returncode,
                        stdout=result_stdout[:200] if result_stdout else "",
                        stderr_preview=result_stderr[:200] if result_stderr else "",
                    )
                    return
                else:
                    logger.error("zoekt_index_failed", repo_id=repo_id, returncode=returncode, stderr=result_stderr)
                    raise RuntimeError(f"Zoekt indexing failed for {repo_id} with exit code {returncode}")

            # Strategy 3: Local with Docker - use volume mount (no docker cp needed)
            # Requires: ./repos/{repo_id} symlink and docker-compose volume: ./repos:/data/repos
            if shutil.which("docker"):
                container_name = os.environ.get("ZOEKT_CONTAINER_NAME", "codegraph-zoekt-index")
                container_repo_path = f"/data/repos/{repo_id}"

                # Check if container is running (async subprocess)
                check_cmd = ["docker", "ps", "-q", "-f", f"name={container_name}"]
                check_proc = await asyncio.create_subprocess_exec(
                    *check_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                check_stdout, _ = await check_proc.communicate()
                check_result_stdout = check_stdout.decode() if check_stdout else ""

                if check_result_stdout.strip():
                    # Run zoekt-index directly - repo accessible via volume mount
                    exec_cmd = [
                        "docker",
                        "exec",
                        container_name,
                        "zoekt-index",
                        "-index",
                        "/data/index",
                        "-ignore_dirs",
                        ",".join(self._ignore_dirs),
                        container_repo_path,
                    ]
                    logger.info("zoekt_docker_exec_starting", repo_id=repo_id, command=" ".join(exec_cmd))
                    # Use asyncio subprocess for non-blocking execution
                    exec_proc = await asyncio.create_subprocess_exec(
                        *exec_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    exec_stdout, exec_stderr = await exec_proc.communicate()
                    exec_result_stdout = exec_stdout.decode() if exec_stdout else ""
                    exec_result_stderr = exec_stderr.decode() if exec_stderr else ""
                    exec_returncode = exec_proc.returncode

                    # Zoekt sometimes returns non-zero even on success
                    # Check for success indicators in output
                    stderr_lower = exec_result_stderr.lower()
                    is_success = (
                        exec_returncode == 0 or "finished shard" in stderr_lower or "files processed" in stderr_lower
                    )

                    if is_success:
                        logger.info(
                            "zoekt_docker_exec_completed",
                            repo_id=repo_id,
                            returncode=exec_returncode,
                            stdout=exec_result_stdout[:200] if exec_result_stdout else "",
                            stderr_preview=exec_result_stderr[:200] if exec_result_stderr else "",
                        )
                        return
                    else:
                        logger.error(
                            "zoekt_docker_exec_failed",
                            repo_id=repo_id,
                            returncode=exec_returncode,
                            stderr=exec_result_stderr,
                        )
                        msg = f"Zoekt docker indexing failed for {repo_id}"
                        raise RuntimeError(f"{msg} with exit code {exec_returncode}")
                else:
                    logger.warning(
                        "zoekt_container_not_running",
                        container_name=container_name,
                        message=f"Container {container_name} is not running. Start it with docker-compose.",
                    )

            # No zoekt-index available
            logger.warning(
                "zoekt_index_not_available",
                repo_id=repo_id,
                message="zoekt-index not found. Install zoekt or start Docker container.",
            )
        except Exception as e:
            # Catch any other errors (file system, permission, etc.)
            logger.error("zoekt_index_error", repo_id=repo_id, error=str(e))
            raise

    async def reindex_paths(self, repo_id: str, snapshot_id: str, paths: list[str]) -> None:
        """
        Partial reindex for specific files using Zoekt incremental indexing.

        Strategy:
        1. Use zoekt-index with -incremental flag for efficient updates
        2. For small changes (<10 files), run incremental index
        3. For large changes (>=10 files), fallback to full reindex for better performance

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            paths: List of file paths to reindex
        """
        if not paths:
            logger.info("zoekt_reindex_paths_empty", repo_id=repo_id)
            return

        repo_path = self.repo_resolver.get_fs_path(repo_id)

        if not repo_path.exists():
            logger.error("zoekt_repo_path_not_found", repo_path=str(repo_path), repo_id=repo_id)
            raise FileNotFoundError(f"Repository not found: {repo_id}")

        # Determine strategy: incremental vs full reindex
        INCREMENTAL_THRESHOLD = 10
        use_incremental = len(paths) < INCREMENTAL_THRESHOLD

        if not use_incremental:
            logger.info(
                "zoekt_large_change_full_reindex",
                repo_id=repo_id,
                paths_count=len(paths),
                threshold=INCREMENTAL_THRESHOLD,
            )
            await self.reindex_repo(repo_id, snapshot_id)
            return

        # Incremental reindex using Zoekt's -incremental flag
        # Note: Zoekt doesn't support file-list, it scans directory and detects changes via mtime
        try:
            import asyncio
            import os
            import shutil

            env = os.environ.copy()
            if os.path.exists("/data/index"):
                env["ZOEKT_INDEX_ROOT"] = "/data/index"

            index_dir = Path(self.zoekt_index_dir)
            index_dir.mkdir(parents=True, exist_ok=True)

            # Check for zoekt-index binary
            zoekt_cmd = shutil.which(self.zoekt_index_cmd)
            if not zoekt_cmd:
                # Try go bin path
                go_bin_path = Path.home() / "go" / "bin" / self.zoekt_index_cmd
                if go_bin_path.exists():
                    zoekt_cmd = str(go_bin_path)
                else:
                    logger.warning("zoekt_index_not_found", repo_id=repo_id)
                    return

            cmd = [
                zoekt_cmd,
                "-index",
                str(index_dir),
                "-incremental",  # Only reindex files with changed mtime
                "-ignore_dirs",
                ",".join(self._ignore_dirs),
                str(repo_path),
            ]
            logger.info(
                "zoekt_incremental_index_starting",
                repo_id=repo_id,
                paths_count=len(paths),
            )
            # Use asyncio subprocess for non-blocking execution
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd, stderr.decode() if stderr else "")
            logger.info(
                "zoekt_incremental_index_completed",
                repo_id=repo_id,
                paths_count=len(paths),
            )

        except subprocess.CalledProcessError as e:
            logger.error("zoekt_incremental_index_failed", repo_id=repo_id, stderr=e.stderr)
            logger.warning("zoekt_fallback_to_full_reindex", repo_id=repo_id)
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
                query=zoekt_query,
                limit=limit * 3,  # Request more for mapping fallback
            )
        except Exception as e:
            logger.error("zoekt_search_failed", repo_id=repo_id, query=query[:50], error=str(e))
            return []

        # Step 1: Collect all (file_path, line) locations from Zoekt results
        match_locations: list[tuple[str, int, str, float]] = []  # (file, line, context, score)
        for file_match in file_matches:
            if not file_match.Matches:
                continue
            for match in file_match.Matches:
                match_locations.append(
                    (
                        file_match.FileName,
                        match.LineNum,
                        self._extract_context(match),
                        1.0,  # Base score
                    )
                )

        if not match_locations:
            return []

        # Step 2: Batch fetch chunks for all locations (N+1 방지)
        locations_to_query = [(fp, line) for fp, line, _, _ in match_locations]
        chunk_map = await self._get_chunks_batch(repo_id, locations_to_query)

        # Step 3: Build SearchHits from batch results
        hits: list[SearchHit] = []
        mapping_stats = {"exact": 0, "file_fallback": 0, "virtual": 0}

        for file_path, line, context, base_score in match_locations:
            chunk = chunk_map.get((file_path, line))

            if chunk:
                # Exact mapping found
                mapping_stats["exact"] += 1
                hits.append(
                    SearchHit(
                        chunk_id=chunk.chunk_id,
                        file_path=file_path,
                        symbol_id=chunk.symbol_id,
                        score=base_score,
                        source="lexical",
                        metadata={
                            "line": line,
                            "preview": context,
                            "kind": chunk.kind,
                            "mapped": True,
                            "match_type": "exact",
                        },
                    )
                )
            else:
                # Fallback to virtual chunk
                mapping_stats["virtual"] += 1
                hits.append(
                    SearchHit(
                        chunk_id=f"virtual:{repo_id}:{file_path}:{line}",
                        file_path=file_path,
                        symbol_id=None,
                        score=base_score * 0.5,
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
                )

        # Sort by score (exact matches first)
        hits.sort(key=lambda h: h.score, reverse=True)

        # Log mapping stats
        logger.info(
            "zoekt_chunk_mapping_complete",
            repo_id=repo_id,
            exact_matches=mapping_stats["exact"],
            file_fallback=mapping_stats["file_fallback"],
            virtual_matches=mapping_stats["virtual"],
            total_hits=len(hits),
        )

        return hits[:limit]

    async def _get_chunks_batch(self, repo_id: str, locations: list[tuple[str, int]]) -> dict[tuple[str, int], Any]:
        """
        Batch fetch chunks for multiple (file_path, line) locations.

        Uses ChunkStore.find_chunks_by_file_and_lines_batch if available,
        otherwise falls back to sequential queries.
        """
        if hasattr(self.chunk_store, "find_chunks_by_file_and_lines_batch"):
            try:
                return await self.chunk_store.find_chunks_by_file_and_lines_batch(repo_id, locations)
            except Exception as e:
                logger.warning(
                    "zoekt_batch_chunk_lookup_failed",
                    repo_id=repo_id,
                    locations_count=len(locations),
                    error=str(e),
                    fallback="sequential",
                )

        # Fallback to sequential (for stores without batch support)
        result = {}
        for file_path, line in locations:
            chunk = await self._get_chunk_async(repo_id, file_path, line)
            if chunk:
                result[(file_path, line)] = chunk
        return result

    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete Zoekt index for repository.

        Strategy:
        1. Locate Zoekt index files for the repository
        2. Delete shard files matching the repository name
        3. Zoekt index files are typically: {repo}.zoekt

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (unused - Zoekt indexes latest state)
        """
        zoekt_repo = self.repo_resolver.get_zoekt_repo_name(repo_id)

        try:
            # Find Zoekt index directory (typically .zoekt/ or /var/lib/zoekt/)
            # For MVP, assume zoekt stores indexes in default location
            import glob
            import os

            # Common Zoekt index locations
            possible_index_dirs = [
                os.path.expanduser("~/.zoekt"),
                "/var/lib/zoekt",
                "./zoekt_index",
                "./.zoekt",
            ]

            deleted_count = 0
            for index_dir in possible_index_dirs:
                if not os.path.exists(index_dir):
                    continue

                # Find index files for this repo
                # Zoekt creates files like: {repo}_v{version}.{number}.zoekt
                pattern = os.path.join(index_dir, f"{zoekt_repo}*.zoekt")
                index_files = glob.glob(pattern)

                for index_file in index_files:
                    try:
                        os.remove(index_file)
                        deleted_count += 1
                        logger.debug("zoekt_index_file_deleted", file=index_file)
                    except OSError as e:
                        logger.error("zoekt_index_file_delete_failed", file=index_file, error=str(e))

            if deleted_count > 0:
                logger.info("zoekt_index_deleted", repo_id=repo_id, deleted_count=deleted_count)
            else:
                logger.warning("zoekt_index_not_found", repo_id=repo_id)

        except Exception as e:
            logger.error("zoekt_index_deletion_failed", repo_id=repo_id, error=str(e))
            # Don't raise - deletion is best-effort

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
            logger.debug("zoekt_chunk_mapping_failed", file_path=file_path, line=line, error=str(e))
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
            logger.debug("zoekt_file_chunk_mapping_failed", file_path=file_path, error=str(e))
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
