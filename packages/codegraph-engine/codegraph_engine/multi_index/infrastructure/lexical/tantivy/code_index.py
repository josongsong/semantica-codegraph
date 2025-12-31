"""
Tantivy Code Index

Unified Tantivy-based code search.

Architecture (Hexagonal):
- Infrastructure layer (Adapter)
- Implements SearchableIndex Protocol (Port)
- Uses ChunkStore for file → chunk mapping

SOLID:
- SRP: Code indexing and search only
- OCP: Extensible via Protocol
- LSP: SearchableIndex compatible
- ISP: Minimal interface
- DIP: Depends on ChunkStore (abstraction)

Performance (RFC-020 Section 12):
- Index: ~50ms/file
- Search: < 15ms
- Incremental: delete + add (upsert)

Schema (FINAL - Phase 3 정의, 변경 불가):
- content: 코드 본문 (3-gram + CamelCase)
- string_literals: 문자열 리터럴 (3-gram only)
- comments: 주석 (basic + 3-gram, CamelCase OFF)
- docstring: Docstring (basic + 3-gram)
- file_path: 파일 경로 (keyword)
- repo_id: 저장소 ID (keyword)
- indexed_at: 인덱싱 시각 (date)
"""

import asyncio
import multiprocessing
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import tantivy

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.domain.ports import (
    FileToIndex,
    IndexingMode,
    IndexingResult,
)
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit, clamp_search_limit

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.chunk.store import ChunkStore

logger = get_logger(__name__)


class TantivyCodeIndex:
    """
    Tantivy-based code search.

    Features:
    - Unified index
    - BM25 ranking
    - Incremental upsert (delete + add)
    - 7-field schema

    Protocol: SearchableIndex (multi_index/domain/ports.py)
    """

    def __init__(
        self,
        index_dir: str | Path,
        chunk_store: "ChunkStore",
        heap_size_mb: int | None = None,
        num_threads: int | None = None,
        mode: IndexingMode = IndexingMode.BALANCED,
        batch_size: int = 100,
    ):
        """
        Initialize Tantivy Code Index

        Args:
            index_dir: Tantivy index directory
            chunk_store: ChunkStore for file → chunk mapping
            heap_size_mb: Writer heap size (MB). If None, use mode default
            num_threads: Number of indexing threads. If None, use mode default
            mode: Performance mode (CONSERVATIVE/BALANCED/AGGRESSIVE)
            batch_size: Number of files per batch commit (default: 100)

        Raises:
            ValueError: If index_dir or chunk_store is None
        """
        if not index_dir:
            raise ValueError("index_dir cannot be None or empty")

        if not chunk_store:
            raise ValueError("ChunkStore cannot be None")

        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")

        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.chunk_store = chunk_store
        self.mode = mode
        self.batch_size = batch_size

        # Apply mode-based defaults if not explicitly provided
        self.heap_size_mb = heap_size_mb if heap_size_mb is not None else self._get_heap_size(mode)
        self.num_threads = num_threads if num_threads is not None else self._get_num_threads(mode)

        # Build schema and index
        self.schema = self._build_schema()
        self.index = self._get_or_create_index()

        # Singleton writer (performance optimization)
        self._writer = None
        self._writer_lock = asyncio.Lock()

        # Field name cache (tantivy-py doesn't have get_field)
        self._fields = {
            "content": "content",
            "string_literals": "string_literals",
            "comments": "comments",
            "docstring": "docstring",
            "file_path": "file_path",
            "repo_id": "repo_id",
            "indexed_at": "indexed_at",
        }

        logger.info(
            "tantivy_code_index_initialized",
            index_dir=str(self.index_dir),
            mode=mode.value,
            heap_size_mb=self.heap_size_mb,
            num_threads=self.num_threads,
            batch_size=batch_size,
        )

    @staticmethod
    def _get_heap_size(mode: IndexingMode) -> int:
        """Get heap size (MB) based on performance mode"""
        return {
            IndexingMode.CONSERVATIVE: 512,
            IndexingMode.BALANCED: 1024,
            IndexingMode.AGGRESSIVE: 2048,
        }[mode]

    @staticmethod
    def _get_num_threads(mode: IndexingMode) -> int:
        """Get thread count based on performance mode"""
        cpu_count = multiprocessing.cpu_count()
        return {
            IndexingMode.CONSERVATIVE: min(4, cpu_count),
            IndexingMode.BALANCED: min(8, cpu_count),
            IndexingMode.AGGRESSIVE: min(16, cpu_count),
        }[mode]

    def _build_schema(self) -> tantivy.Schema:
        """
        Build Tantivy schema (FINAL - RFC-020 Phase 3)

        ⚠️ 이후 변경 불가 (schema 변경 시 인덱스 재빌드 필요)

        Fields (7):
        1. content: 코드 본문 (stored, 3-gram + CamelCase)
        2. string_literals: 문자열 리터럴 (not stored, 3-gram)
        3. comments: 주석 (not stored, basic + 3-gram)
        4. docstring: Docstring (not stored, basic + 3-gram)
        5. file_path: 파일 경로 (stored, keyword)
        6. repo_id: 저장소 ID (stored, keyword)
        7. indexed_at: 인덱싱 시각 (stored, date)

        Returns:
            Tantivy Schema
        """
        schema_builder = tantivy.SchemaBuilder()

        # 1. 코드 본문 (stored for snippet)
        schema_builder.add_text_field("content", stored=True, tokenizer_name="default")
        # TODO: Custom tokenizer (3-gram + CamelCase) in Phase 4

        # 2-4. 검색 전용 필드 (not stored, 메모리 절약)
        schema_builder.add_text_field("string_literals", stored=False, tokenizer_name="default")
        schema_builder.add_text_field("comments", stored=False, tokenizer_name="default")
        schema_builder.add_text_field("docstring", stored=False, tokenizer_name="default")

        # 5-7. 메타데이터
        schema_builder.add_text_field("file_path", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field("repo_id", stored=True, tokenizer_name="raw")
        schema_builder.add_date_field("indexed_at", stored=True)

        return schema_builder.build()

    def _get_or_create_index(self) -> tantivy.Index:
        """
        Get existing index or create new one

        Returns:
            Tantivy Index
        """
        try:
            # Try to open existing index
            index = tantivy.Index.open(str(self.index_dir))
            logger.info(f"Opened existing Tantivy index: {self.index_dir}")
            return index
        except Exception:
            # Create new index
            index = tantivy.Index(self.schema, path=str(self.index_dir))
            logger.info(f"Created new Tantivy index: {self.index_dir}")
            return index

    async def _get_writer(self):
        """
        Get or create singleton writer (thread-safe)

        Uses double-checked locking for performance.

        Returns:
            Tantivy IndexWriter
        """
        # Fast path: writer already exists
        if self._writer is not None:
            return self._writer

        # Slow path: create writer (thread-safe)
        async with self._writer_lock:
            # Double-check: another thread might have created it
            if self._writer is None:
                try:
                    self._writer = self.index.writer(
                        heap_size=self.heap_size_mb * 1024 * 1024,
                        num_threads=self.num_threads,
                    )
                    logger.debug("Created singleton IndexWriter")
                except Exception as e:
                    logger.error("Failed to create IndexWriter", error=str(e))
                    raise

            return self._writer

    async def _commit_writer(self):
        """
        Commit pending changes

        Note: Writer remains valid after commit (can be reused)
        """
        if self._writer is not None:
            try:
                self._writer.commit()
            except Exception as e:
                logger.error("Writer commit failed", error=str(e))
                # Invalidate writer on error
                self._writer = None
                raise

    async def close(self):
        """
        Close writer and release resources

        Call this on application shutdown
        """
        async with self._writer_lock:
            if self._writer is not None:
                try:
                    self._writer.commit()
                    logger.info("IndexWriter closed gracefully")
                except Exception as e:
                    logger.error("Error closing writer", error=str(e))
                finally:
                    self._writer = None

    def _build_document(self, repo_id: str, file_path: str, content: str) -> tantivy.Document:
        """
        Build Tantivy document from file content

        This method is pure (no side effects) and can be parallelized.

        Args:
            repo_id: Repository ID
            file_path: File path
            content: File content

        Returns:
            Tantivy Document

        Raises:
            ValueError: If required fields are missing
        """
        if not repo_id:
            raise ValueError("repo_id cannot be empty")
        if not file_path:
            raise ValueError("file_path cannot be empty")

        # Extract fields (pure functions)
        string_literals = self._extract_string_literals(content)
        comments = self._extract_comments(content)
        docstrings = self._extract_docstrings(content)

        # Create document
        doc = tantivy.Document()
        doc.add_text(self._fields["file_path"], file_path)
        doc.add_text(self._fields["repo_id"], repo_id)
        doc.add_text(self._fields["content"], content)
        doc.add_text(self._fields["string_literals"], string_literals)
        doc.add_text(self._fields["comments"], comments)
        doc.add_text(self._fields["docstring"], docstrings)
        doc.add_date(self._fields["indexed_at"], datetime.now())

        return doc

    async def index_file(self, repo_id: str, file_path: str, content: str) -> bool:
        """
        Index a single file (backward compatibility wrapper)

        Internally delegates to batch indexing for consistency.

        Args:
            repo_id: Repository ID
            file_path: File path
            content: File content

        Returns:
            Success boolean
        """
        try:
            file_to_index = FileToIndex(repo_id=repo_id, file_path=file_path, content=content)
            result = await self.index_files_batch([file_to_index])
            return result.success_count == 1
        except Exception as e:
            logger.error(f"Tantivy index error: {file_path}", error=str(e))
            return False

    async def index_files_batch(self, files: list[FileToIndex], fail_fast: bool = False) -> IndexingResult:
        """
        Index multiple files in batch (SOTA performance)

        Strategy:
        1. Parallel document building (CPU-bound)
        2. Batch commit (reduces I/O)
        3. Transaction safety (rollback on batch failure)

        Args:
            files: List of files to index
            fail_fast: If True, stop on first error. If False, continue and collect errors.

        Returns:
            IndexingResult with success/failure details

        Raises:
            ValueError: If files list is empty
        """
        if not files:
            raise ValueError("files list cannot be empty")

        start_time = asyncio.get_event_loop().time()
        total_files = len(files)
        success_count = 0
        failed_files: list[tuple[str, str]] = []

        logger.info(f"Starting batch indexing: {total_files} files")

        try:
            # Get singleton writer
            writer = await self._get_writer()

            # Process files in batches
            for batch_start in range(0, total_files, self.batch_size):
                batch_end = min(batch_start + self.batch_size, total_files)
                batch = files[batch_start:batch_end]

                try:
                    # Phase 1: Build documents in parallel (outside lock, CPU-bound)
                    docs_to_add: list[tuple[FileToIndex, tantivy.Document]] = []

                    for file in batch:
                        try:
                            doc = self._build_document(file.repo_id, file.file_path, file.content)
                            docs_to_add.append((file, doc))
                        except Exception as e:
                            error_msg = f"{type(e).__name__}: {str(e)}"
                            failed_files.append((file.file_path, error_msg))
                            logger.warning(f"Failed to build document: {file.file_path}", error=error_msg)
                            if fail_fast:
                                raise

                    # Phase 2: Write + commit atomically (inside lock, I/O-bound)
                    async with self._writer_lock:
                        batch_success = 0
                        failed_in_batch: set[str] = set()  # ✅ Track failures

                        for file, doc in docs_to_add:
                            try:
                                # ✅ Atomic upsert: delete + add in single try block
                                # If add fails after delete, both operations won't be committed
                                writer.delete_documents("file_path", file.file_path)
                                writer.add_document(doc)
                                batch_success += 1

                            except Exception as e:
                                # ✅ Mark as failed (won't be in index after commit)
                                error_msg = f"{type(e).__name__}: {str(e)}"
                                failed_files.append((file.file_path, error_msg))
                                failed_in_batch.add(file.file_path)
                                logger.warning(f"Failed to upsert document: {file.file_path}", error=error_msg)

                                if fail_fast:
                                    raise

                        # ✅ Commit only successful operations
                        # Failed files: delete won't be committed (data preserved)
                        await self._commit_writer()
                        success_count += batch_success

                        logger.debug(
                            f"Batch [{batch_start}:{batch_end}] committed: {batch_success}/{len(batch)} succeeded"
                        )

                except Exception as e:
                    # Batch-level failure
                    batch_error = f"Batch commit failed: {type(e).__name__}: {str(e)}"
                    logger.error(batch_error)

                    # ✅ Mark all files in this batch as failed (O(n) with set)
                    failed_paths_set = {f[0] for f in failed_files}
                    for file in batch:
                        if file.file_path not in failed_paths_set:
                            failed_files.append((file.file_path, batch_error))
                            failed_paths_set.add(file.file_path)

                    if fail_fast:
                        raise

            duration = asyncio.get_event_loop().time() - start_time

            logger.info(
                f"Batch indexing complete: {success_count}/{total_files} succeeded "
                f"in {duration:.2f}s ({total_files / duration:.1f} files/s)"
            )

            return IndexingResult(
                total_files=total_files,
                success_count=success_count,
                failed_files=failed_files,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.error("Batch indexing failed catastrophically", error=str(e))

            # Return partial result
            return IndexingResult(
                total_files=total_files,
                success_count=success_count,
                failed_files=failed_files,
                duration_seconds=duration,
            )

    async def delete_file(self, repo_id: str, file_path: str) -> bool:
        """
        Delete a file from index

        Args:
            repo_id: Repository ID
            file_path: File path

        Returns:
            Success boolean
        """
        try:
            # Get singleton writer
            writer = await self._get_writer()

            async with self._writer_lock:
                writer.delete_documents("file_path", file_path)
                await self._commit_writer()

            logger.debug(f"Deleted file: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Tantivy delete error: {file_path}", error=str(e))
            return False

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Search code (implements SearchableIndex Protocol)

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID (unused, for Protocol compatibility)
            query: Search query
            limit: Maximum results

        Returns:
            List of SearchHit objects
        """
        limit = clamp_search_limit(limit)

        try:
            searcher = self.index.searcher()

            # Parse query: repo_id filter + content search
            query_parser = tantivy.QueryParser.for_index(
                self.index,
                [
                    self._fields["content"],
                    self._fields["string_literals"],
                    self._fields["comments"],
                    self._fields["docstring"],
                ],
            )

            # Build query: repo_id AND (content OR literals OR comments OR docstring)
            parsed_query = query_parser.parse_query(f'repo_id:"{repo_id}" AND {query}')

            # Execute search
            top_docs = searcher.search(parsed_query, limit)

            # Convert to SearchHit
            hits = []
            for score, doc_address in top_docs:
                doc = searcher.doc(doc_address)

                file_path = doc.get_first(self._fields["file_path"])
                content = doc.get_first(self._fields["content"])

                # Map file → chunk via ChunkStore
                chunk_id = await self._map_file_to_chunk(repo_id, file_path)

                # Create SearchHit
                hit = SearchHit(
                    chunk_id=chunk_id,
                    symbol_id="",  # Lexical search doesn't have symbol
                    file_path=file_path or "",
                    score=float(score),
                    source="lexical",
                    metadata={
                        "preview": content[:200] if content else "",
                        "engine": "tantivy",
                    },
                )
                hits.append(hit)

            logger.debug(f"Tantivy search: '{query}' → {len(hits)} hits")
            return hits

        except Exception as e:
            logger.error(f"Tantivy search error: {query}", error=str(e))
            return []

    async def _map_file_to_chunk(self, repo_id: str, file_path: str, line: int = 1) -> str:
        """
        Map file+line to chunk ID via ChunkStore (Real, not Stub)

        Priority:
        1. Function/method chunk (most specific)
        2. Class chunk
        3. File chunk (fallback)

        Args:
            repo_id: Repository ID
            file_path: File path
            line: Line number (default: 1)

        Returns:
            Chunk ID

        Raises:
            ValueError: If ChunkStore has no chunks for this file
        """
        try:
            # 1. Try function/class chunk at line
            chunk = await self.chunk_store.find_chunk_by_file_and_line(repo_id, file_path, line)
            if chunk:
                return chunk.id

            # 2. Fallback: file-level chunk
            file_chunk = await self.chunk_store.find_file_chunk(repo_id, file_path)
            if file_chunk:
                return file_chunk.id

            # 3. No chunks found - this is an error case
            # Tantivy returned a file that ChunkStore doesn't know about
            logger.warning(f"No chunks found for file: {file_path}")

            # Fallback: virtual chunk ID (for robustness)
            return f"chunk:{repo_id}:{file_path}:virtual"

        except Exception as e:
            logger.error(f"ChunkStore mapping error: {file_path}", error=str(e))
            # Fallback to virtual chunk (don't crash search)
            return f"chunk:{repo_id}:{file_path}:error"

    def _extract_string_literals(self, content: str) -> str:
        """
        Extract string literals from code

        Simple regex-based extraction (Python/JS/TS)

        Args:
            content: Code content

        Returns:
            Concatenated string literals
        """
        # Match: "..." or '...' or """...""" or '''...'''
        pattern = r"""["']{1,3}(.*?)["']{1,3}"""
        matches = re.findall(pattern, content, re.DOTALL)

        return " ".join(matches)

    def _extract_comments(self, content: str) -> str:
        """
        Extract comments from code

        Supports: # (Python), // (JS/TS), /* */ (multi-line)

        Args:
            content: Code content

        Returns:
            Concatenated comments
        """
        comments = []

        # Python/Bash: # ...
        comments.extend(re.findall(r"#\s*(.+)", content))

        # JS/TS/Java: // ...
        comments.extend(re.findall(r"//\s*(.+)", content))

        # Multi-line: /* ... */
        comments.extend(re.findall(r"/\*\s*(.+?)\s*\*/", content, re.DOTALL))

        return " ".join(comments)

    def _extract_docstrings(self, content: str) -> str:
        """
        Extract docstrings (Python)

        Args:
            content: Code content

        Returns:
            Concatenated docstrings
        """
        # Python docstrings: """...""" or '''...''' at function/class start
        pattern = r'(?:def |class ).+?:\s*["\']{{3}}(.+?)["\']{{3}}'
        matches = re.findall(pattern, content, re.DOTALL)

        return " ".join(matches)
