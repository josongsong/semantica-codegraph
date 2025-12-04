"""
Chunk Hierarchy Builder

Builds 6-level chunk hierarchy from IR + Graph:
    Repo → Project → Module → File → Class → Function

Optimizations:
- O(1) parent lookup via indexing
- Centralized FQN generation
- Symbol visibility extraction
- Content hash caching

Observability (GAP I1):
- Structured logging for chunk building operations
- Metrics for chunk counts by kind and timing
"""

import hashlib
import time
from collections import defaultdict
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from src.common.observability import get_logger, record_counter, record_histogram
from src.contexts.code_foundation.infrastructure.chunk.boundary import ChunkBoundaryValidator
from src.contexts.code_foundation.infrastructure.chunk.builder_graphfirst import map_graph_kind_to_chunk_kind
from src.contexts.code_foundation.infrastructure.chunk.fqn_builder import FQNBuilder
from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdContext, ChunkIdGenerator
from src.contexts.code_foundation.infrastructure.chunk.mapping import ChunkGraphMapper, ChunkMapper
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, ChunkToGraph, ChunkToIR
from src.contexts.code_foundation.infrastructure.chunk.test_detector import TestDetector
from src.contexts.code_foundation.infrastructure.chunk.visibility import VisibilityExtractor

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument, Node

logger = get_logger(__name__)


class ChunkBuilder:
    """
    Builds chunk hierarchy from IR + Graph documents.

    Usage:
        builder = ChunkBuilder(ChunkIdGenerator())
        chunks = builder.build(
            repo_id="myrepo",
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=["line1", "line2", ...],
            repo_config={"root": "/path/to/repo"},
        )

    Optimizations:
    - O(1) parent lookup via file_path and span indexing
    - Centralized FQN builder for consistency
    - Automatic visibility extraction
    - Content hash caching
    """

    def __init__(
        self,
        id_generator: ChunkIdGenerator,
        boundary_validator: ChunkBoundaryValidator | None = None,
        chunk_mapper: ChunkMapper | None = None,
        graph_mapper: ChunkGraphMapper | None = None,
    ):
        self._id_gen = id_generator
        self._boundary_validator = boundary_validator or ChunkBoundaryValidator()
        self._chunk_mapper = chunk_mapper or ChunkMapper()
        self._graph_mapper = graph_mapper or ChunkGraphMapper()
        self._chunks: list[Chunk] = []
        self._project_chunks: list[Chunk] = []  # Store project chunks for reuse
        self._md5_hasher = hashlib.md5  # Cache MD5 hasher reference

        # Performance Optimization: Parent lookup indexes
        self._file_chunk_index: dict[str, Chunk] = {}  # file_path → Chunk (O(1) lookup)
        self._class_chunk_index: dict[str, list[Chunk]] = defaultdict(list)  # file_path → [Chunks]

        # Performance Optimization: Content hash cache
        self._code_hash_cache: dict[tuple[int, int], str] = {}  # (start_line, end_line) → hash

        # Utilities
        self._fqn_builder = FQNBuilder()
        self._visibility_extractor = VisibilityExtractor()
        self._test_detector = TestDetector()  # P1: Test detection

    def build(
        self,
        repo_id: str,
        ir_doc: "IRDocument",
        graph_doc: "GraphDocument",
        file_text: list[str],
        repo_config: dict,
        snapshot_id: str | None = None,
        is_overlay: bool = False,
        overlay_session_id: str | None = None,
    ) -> tuple[list[Chunk], ChunkToIR, ChunkToGraph]:
        """
        Build complete chunk hierarchy for a file.

        Args:
            repo_id: Repository identifier
            ir_doc: IR document for the file
            graph_doc: Graph document with semantic info
            file_text: Source code lines
            repo_config: Repository configuration (project roots, etc.)
            snapshot_id: Git commit hash or timestamp (defaults to "default")
            is_overlay: True if building overlay chunks (IDE unsaved changes)
            overlay_session_id: IDE session ID (required if is_overlay=True)

        Returns:
            Tuple of (chunks, chunk_to_ir, chunk_to_graph)
        """
        start_time = time.perf_counter()
        self._chunks = []
        snapshot_id = snapshot_id or "default"

        # GAP I1: Log build start
        logger.info(
            "chunk_build_start",
            repo_id=repo_id,
            snapshot_id=snapshot_id[:8] if len(snapshot_id) > 8 else snapshot_id,
            file_lines=len(file_text),
            ir_nodes=len(ir_doc.nodes),
            graph_nodes=len(graph_doc.graph_nodes),
        )
        record_counter("chunk_build_total")

        # Performance Optimization: Initialize indexes
        self._file_chunk_index = {}
        self._class_chunk_index = defaultdict(list)
        self._code_hash_cache = {}

        # CRITICAL FIX: Normalize file_text to ensure consistent content_hash
        # Remove trailing newlines that may be present from readlines()
        file_text = self._normalize_file_text(file_text)

        # 1. Build structural hierarchy: Repo → Project → Module → File
        repo_chunk = self._build_repo_chunk(repo_id, repo_config, snapshot_id)
        project_chunks = self._build_project_chunks(repo_chunk, repo_config, snapshot_id)
        self._project_chunks = project_chunks  # Store for reuse in _build_file_chunks
        module_chunks = self._build_module_chunks(project_chunks, ir_doc, snapshot_id)
        file_chunks = self._build_file_chunks(module_chunks, ir_doc, file_text, snapshot_id)

        # Performance Optimization: Index file chunks for O(1) lookup
        for file_chunk in file_chunks:
            if file_chunk.file_path:
                self._file_chunk_index[file_chunk.file_path] = file_chunk

        # 2. Build symbol hierarchy: Class → Function
        # Graph-First: Pass graph_doc to use Graph as single source of truth
        class_chunks = self._build_class_chunks(file_chunks, ir_doc, graph_doc, file_text, snapshot_id)

        # Performance Optimization: Index class chunks for O(k) lookup (k = classes per file)
        for class_chunk in class_chunks:
            if class_chunk.file_path:
                self._class_chunk_index[class_chunk.file_path].append(class_chunk)

        func_chunks = self._build_function_chunks(class_chunks, file_chunks, ir_doc, graph_doc, file_text, snapshot_id)

        # 3. Build P1 chunks: Docstring, File Header, Skeleton
        docstring_chunks = self._build_docstring_chunks(class_chunks, func_chunks, ir_doc, file_text, snapshot_id)
        file_header_chunks = self._build_file_header_chunks(file_chunks, ir_doc, file_text, snapshot_id)
        skeleton_chunks = self._build_skeleton_chunks(
            file_chunks, class_chunks, func_chunks, ir_doc, file_text, snapshot_id
        )

        # 4. Build P2 chunks: Usage
        usage_chunks = self._build_usage_chunks(func_chunks, ir_doc, file_text, snapshot_id)

        # Collect all chunks
        chunks = [
            repo_chunk,
            *project_chunks,
            *module_chunks,
            *file_chunks,
            *class_chunks,
            *func_chunks,
            *docstring_chunks,
            *file_header_chunks,
            *skeleton_chunks,
            *usage_chunks,
        ]

        # P2: Mark chunks as overlay if requested
        if is_overlay:
            for chunk in chunks:
                chunk.is_overlay = True
                chunk.overlay_session_id = overlay_session_id

        # 5. Build mappings & validate
        chunk_to_ir, chunk_to_graph = self._build_mappings(chunks, ir_doc, graph_doc)
        self._validate_boundaries(chunks)

        # GAP I1: Log build completion with metrics
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "chunk_build_complete",
            repo_id=repo_id,
            total_chunks=len(chunks),
            repo_chunks=1,
            project_chunks=len(project_chunks),
            module_chunks=len(module_chunks),
            file_chunks=len(file_chunks),
            class_chunks=len(class_chunks),
            func_chunks=len(func_chunks),
            docstring_chunks=len(docstring_chunks),
            file_header_chunks=len(file_header_chunks),
            skeleton_chunks=len(skeleton_chunks),
            usage_chunks=len(usage_chunks),
            elapsed_ms=round(elapsed_ms, 2),
        )
        record_histogram("chunk_build_duration_ms", elapsed_ms)
        record_histogram("chunk_build_total_count", len(chunks))
        record_histogram("chunk_build_class_count", len(class_chunks))
        record_histogram("chunk_build_function_count", len(func_chunks))

        return chunks, chunk_to_ir, chunk_to_graph

    # ============================================================
    # Structural Hierarchy: Repo → Project → Module → File
    # ============================================================

    def _build_repo_chunk(self, repo_id: str, repo_config: dict, snapshot_id: str) -> Chunk:
        """
        Build repository root chunk.

        Args:
            repo_id: Repository identifier
            repo_config: Repository configuration
            snapshot_id: Git commit hash or timestamp

        Returns:
            Repo chunk
        """
        ctx = ChunkIdContext(repo_id=repo_id, kind="repo", fqn=repo_id)
        chunk_id = self._id_gen.generate(ctx)

        return Chunk(
            chunk_id=chunk_id,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            project_id=None,
            module_path=None,
            file_path=None,
            kind="repo",
            fqn=repo_id,
            start_line=None,
            end_line=None,
            original_start_line=None,
            original_end_line=None,
            content_hash=None,
            parent_id=None,  # Root has no parent
            children=[],
            language=None,
            symbol_visibility=None,
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        )

    def _build_project_chunks(self, repo_chunk: Chunk, repo_config: dict, snapshot_id: str) -> list[Chunk]:
        """
        Build project chunks within repository.

        For MVP: Single project per repo. Multi-project support later.

        Args:
            repo_chunk: Parent repo chunk
            repo_config: Repository configuration
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of project chunks
        """
        # MVP: Single default project
        project_name = repo_config.get("project_name", "default")
        ctx = ChunkIdContext(repo_id=repo_chunk.repo_id, kind="project", fqn=project_name)
        chunk_id = self._id_gen.generate(ctx)

        project_chunk = Chunk(
            chunk_id=chunk_id,
            repo_id=repo_chunk.repo_id,
            snapshot_id=snapshot_id,
            project_id=chunk_id,
            module_path=None,
            file_path=None,
            kind="project",
            fqn=project_name,
            start_line=None,
            end_line=None,
            original_start_line=None,
            original_end_line=None,
            content_hash=None,
            parent_id=repo_chunk.chunk_id,
            children=[],
            language=None,
            symbol_visibility=None,
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
            attrs={},
        )

        # Link parent → child
        repo_chunk.children.append(chunk_id)

        return [project_chunk]

    def _build_module_chunks(self, project_chunks: list[Chunk], ir_doc: "IRDocument", snapshot_id: str) -> list[Chunk]:
        """
        Build module chunks from file path structure.

        Example: "backend/search/retriever.py" → ["backend", "backend.search"]

        Args:
            project_chunks: Parent project chunks
            ir_doc: IR document
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of module chunks
        """
        # Get file nodes from IR
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]
        if not file_nodes:
            return []

        # For MVP: Single file processing
        file_node = file_nodes[0]
        file_path = file_node.file_path

        # Extract module hierarchy from path (cross-platform compatible)
        # Example: "backend/search/retriever.py" → ["backend", "search"]
        # Use PurePosixPath since file paths in IR are always forward-slash separated
        parts = PurePosixPath(file_path).parts
        if len(parts) <= 1:
            return []  # No modules for single-level files

        # Generate module chunks for each directory level
        module_chunks = []
        parent_chunk = project_chunks[0]  # MVP: Single project
        current_fqn = ""

        for _i, part in enumerate(parts[:-1]):  # Exclude file name
            # Build FQN
            if current_fqn:
                current_fqn += f".{part}"
            else:
                current_fqn = part

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="module", fqn=current_fqn)
            chunk_id = self._id_gen.generate(ctx)

            # Create module chunk
            module_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=parent_chunk.project_id,
                module_path=current_fqn,
                file_path=None,
                kind="module",
                fqn=current_fqn,
                start_line=None,
                end_line=None,
                original_start_line=None,
                original_end_line=None,
                content_hash=None,
                parent_id=parent_chunk.chunk_id,
                children=[],
                language=file_node.language,
                symbol_visibility=None,
                symbol_id=None,
                symbol_owner_id=None,
                summary=None,
                importance=None,
                attrs={},
            )

            # Link parent → child
            parent_chunk.children.append(chunk_id)

            module_chunks.append(module_chunk)
            parent_chunk = module_chunk  # Next level parent

        return module_chunks

    def _build_file_chunks(
        self,
        module_chunks: list[Chunk],
        ir_doc: "IRDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build file chunks from IR file nodes.

        Args:
            module_chunks: Parent module chunks
            ir_doc: IR document
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of file chunks
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]
        if not file_nodes:
            return []

        file_chunks = []

        for file_node in file_nodes:
            # Determine parent (module or project)
            if module_chunks:
                parent_chunk = module_chunks[-1]  # Deepest module
            else:
                # If no modules, parent is project (use stored project_chunks)
                if not self._project_chunks:
                    raise ValueError("No project chunks available. Call build() first.")
                parent_chunk = self._project_chunks[0]  # MVP: Single project

            # Build FQN from file path using centralized builder
            # Example: "backend/search/retriever.py" → "backend.search.retriever"
            file_path = file_node.file_path
            fqn = self._fqn_builder.from_file_path(file_path, file_node.language or "python")

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="file", fqn=fqn)
            chunk_id = self._id_gen.generate(ctx)

            # Calculate content hash
            file_content = "".join(file_text)
            content_hash = self._compute_content_hash(file_content)

            # Create file chunk
            file_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=parent_chunk.project_id,
                module_path=parent_chunk.module_path,
                file_path=file_path,
                kind="file",
                fqn=fqn,
                start_line=1,
                end_line=len(file_text),
                original_start_line=1,
                original_end_line=len(file_text),
                content_hash=content_hash,
                parent_id=parent_chunk.chunk_id,
                children=[],
                language=file_node.language,
                symbol_visibility="public",  # Files are public by default
                symbol_id=file_node.id,
                symbol_owner_id=file_node.id,
                summary=None,
                importance=None,
                attrs={},
            )

            # Link parent → child
            parent_chunk.children.append(chunk_id)

            file_chunks.append(file_chunk)

        return file_chunks

    # ============================================================
    # Symbol Hierarchy: Class → Function
    # ============================================================

    def _build_class_chunks(
        self,
        file_chunks: list[Chunk],
        ir_doc: "IRDocument",
        graph_doc: "GraphDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build class chunks from IR class nodes.

        Graph-First Strategy: Uses GraphDocument as single source of truth
        for semantic kinds (service, repository, config, etc.)

        Args:
            file_chunks: Parent file chunks
            ir_doc: IR document
            graph_doc: Graph document (semantic layer)
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of class chunks (including extended types)
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        class_chunks = []

        for class_node in class_nodes:
            # Find parent file chunk
            parent_file = self._find_parent_file_chunk(file_chunks, class_node)
            if not parent_file:
                continue

            # Graph-First: Query Graph for semantic kind (single source of truth)
            graph_node = graph_doc.get_node(class_node.id)
            if graph_node:
                chunk_kind = map_graph_kind_to_chunk_kind(graph_node.kind)
            else:
                # Fallback to "class" if node not found in graph
                chunk_kind = "class"

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind=chunk_kind, fqn=class_node.fqn)
            chunk_id = self._id_gen.generate(ctx)

            # Extract class code for content hash (with caching)
            span_key = (class_node.span.start_line, class_node.span.end_line)
            class_code = self._extract_code_span(file_text, class_node.span.start_line, class_node.span.end_line)
            content_hash = self._compute_content_hash_cached(class_code, span_key)

            # Extract symbol visibility (Python: _private, __dunder)
            symbol_visibility = self._visibility_extractor.extract(class_node, class_node.language)

            # P1: Detect if test class
            decorators = class_node.attrs.get("decorators", []) if class_node.attrs else []
            is_test = self._test_detector.is_test_class(
                name=class_node.name,
                file_path=class_node.file_path,
                language=class_node.language,
                decorators=decorators,
            )

            # Create class chunk
            class_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=parent_file.project_id,
                module_path=parent_file.module_path,
                file_path=class_node.file_path,
                kind=chunk_kind,  # Phase 3: May be service/repository/etc.
                fqn=class_node.fqn,
                start_line=class_node.span.start_line,
                end_line=class_node.span.end_line,
                original_start_line=class_node.span.start_line,
                original_end_line=class_node.span.end_line,
                content_hash=content_hash,
                parent_id=parent_file.chunk_id,
                children=[],
                language=class_node.language,
                symbol_visibility=symbol_visibility,  # Extracted from name/attrs
                symbol_id=class_node.id,
                symbol_owner_id=class_node.id,
                summary=None,
                importance=None,
                attrs={"role": class_node.role} if class_node.role else {},
                is_test=is_test,  # P1: Test detection
            )

            # Link parent → child
            parent_file.children.append(chunk_id)

            class_chunks.append(class_chunk)

        return class_chunks

    def _build_function_chunks(
        self,
        class_chunks: list[Chunk],
        file_chunks: list[Chunk],
        ir_doc: "IRDocument",
        graph_doc: "GraphDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build function/method chunks (leaf chunks).

        Graph-First Strategy: Functions are always "function" kind,
        but graph_doc is available for future extensions.

        Args:
            class_chunks: Parent class chunks
            file_chunks: Parent file chunks (for top-level functions)
            ir_doc: IR document
            graph_doc: Graph document (for future use)
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of function chunks
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        func_nodes = [n for n in ir_doc.nodes if n.kind in (NodeKind.FUNCTION, NodeKind.METHOD)]
        func_chunks = []

        for func_node in func_nodes:
            # Determine parent (class or file)
            if func_node.kind == NodeKind.METHOD:
                parent_chunk = self._find_parent_class_chunk(class_chunks, func_node)
            else:
                parent_chunk = self._find_parent_file_chunk(file_chunks, func_node)

            if not parent_chunk:
                continue

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="function", fqn=func_node.fqn)
            chunk_id = self._id_gen.generate(ctx)

            # Extract function code for content hash (with caching)
            span_key = (func_node.span.start_line, func_node.span.end_line)
            func_code = self._extract_code_span(file_text, func_node.span.start_line, func_node.span.end_line)
            content_hash = self._compute_content_hash_cached(func_code, span_key)

            # Extract symbol visibility
            symbol_visibility = self._visibility_extractor.extract(func_node, func_node.language)

            # P1: Detect if test function
            decorators = func_node.attrs.get("decorators", []) if func_node.attrs else []
            is_test = self._test_detector.is_test_function(
                name=func_node.name,
                file_path=func_node.file_path,
                language=func_node.language,
                decorators=decorators,
            )

            # Create function chunk
            func_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=parent_chunk.project_id,
                module_path=parent_chunk.module_path,
                file_path=func_node.file_path,
                kind="function",
                fqn=func_node.fqn,
                start_line=func_node.span.start_line,
                end_line=func_node.span.end_line,
                original_start_line=func_node.span.start_line,
                original_end_line=func_node.span.end_line,
                content_hash=content_hash,
                parent_id=parent_chunk.chunk_id,
                children=[],  # Leaf - no children
                language=func_node.language,
                symbol_visibility=symbol_visibility,  # Extracted from name/attrs
                symbol_id=func_node.id,
                symbol_owner_id=func_node.id,
                summary=None,
                importance=None,
                attrs={},
                is_test=is_test,  # P1: Test detection
            )

            # Link parent → child
            parent_chunk.children.append(chunk_id)

            func_chunks.append(func_chunk)

        return func_chunks

    # ============================================================
    # Helpers
    # ============================================================

    def _find_parent_file_chunk(self, file_chunks: list[Chunk], node: "Node") -> Chunk | None:
        """
        Find the file chunk containing this node.

        Performance Optimization: O(1) hash lookup instead of O(n) linear search.
        """
        return self._file_chunk_index.get(node.file_path)

    def _find_parent_class_chunk(self, class_chunks: list[Chunk], node: "Node") -> Chunk | None:
        """
        Find the class chunk containing this node (for methods).

        Performance Optimization: O(k) where k = classes in file (usually < 10),
        instead of O(n) where n = all classes in project.
        """
        # Get candidate class chunks in same file (O(1) hash lookup)
        candidates = self._class_chunk_index.get(node.file_path, [])

        # Find containing class (O(k) where k is small)
        for class_chunk in candidates:
            if (
                class_chunk.start_line is not None
                and class_chunk.end_line is not None
                and node.span.start_line >= class_chunk.start_line
                and node.span.end_line <= class_chunk.end_line
            ):
                return class_chunk
        return None

    def _find_parent_chunk_by_span(self, chunks: list[Chunk], start_line: int, end_line: int) -> Chunk | None:
        """Find the chunk containing this span (for extended chunks)."""
        for chunk in chunks:
            if (
                chunk.start_line is not None
                and chunk.end_line is not None
                and start_line >= chunk.start_line
                and end_line <= chunk.end_line
            ):
                return chunk
        return None

    def _find_parent_chunk_by_path(self, chunks: list[Chunk], path: str | None) -> Chunk | None:
        """Find the chunk matching this file path."""
        if path is None:
            return None
        for chunk in chunks:
            if chunk.file_path == path:
                return chunk
        return None

    def _normalize_file_text(self, file_text: list[str]) -> list[str]:
        """
        Normalize file text to ensure consistent content_hash.

        Removes trailing newlines that may be present from readlines().
        This ensures content_hash is consistent regardless of how file_text was created.

        Args:
            file_text: Raw file text lines (may have trailing newlines)

        Returns:
            Normalized file text lines (no trailing newlines)
        """
        return [line.rstrip("\n\r") for line in file_text]

    def _extract_code_span(self, file_text: list[str], start_line: int, end_line: int) -> str:
        """Extract code from file text for a given line range."""
        # Lines are 1-indexed in span, but list is 0-indexed
        # file_text is already normalized (no trailing newlines)
        return "\n".join(file_text[start_line - 1 : end_line])

    def _compute_content_hash(self, content: str) -> str:
        """
        Compute MD5 hash for content.

        Centralized hash computation to avoid code duplication.

        Args:
            content: Content to hash

        Returns:
            MD5 hexdigest
        """
        return self._md5_hasher(content.encode()).hexdigest()

    def _compute_content_hash_cached(self, content: str, span_key: tuple[int, int]) -> str:
        """
        Compute MD5 hash with caching.

        Performance Optimization: Avoid re-computing hash for same span.

        Args:
            content: Content to hash
            span_key: (start_line, end_line) for cache key

        Returns:
            MD5 hexdigest
        """
        if span_key in self._code_hash_cache:
            return self._code_hash_cache[span_key]

        hash_value = self._md5_hasher(content.encode()).hexdigest()
        self._code_hash_cache[span_key] = hash_value
        return hash_value

    def _build_mappings(
        self, chunks: list[Chunk], ir_doc: "IRDocument", graph_doc: "GraphDocument"
    ) -> tuple[ChunkToIR, ChunkToGraph]:
        """
        Build Chunk ↔ IR/Graph mappings.

        Args:
            chunks: List of chunks
            ir_doc: IR document
            graph_doc: Graph document

        Returns:
            Tuple of (chunk_to_ir, chunk_to_graph)
        """
        # Map chunks to IR nodes
        chunk_to_ir = self._chunk_mapper.map_ir(chunks, ir_doc)

        # Map chunks to graph nodes
        chunk_to_graph = self._graph_mapper.map_graph(chunks, graph_doc)

        return chunk_to_ir, chunk_to_graph

    def _validate_boundaries(self, chunks: list[Chunk]):
        """
        Validate chunk boundaries (no gaps/overlaps).

        Raises:
            BoundaryValidationError: If validation fails
        """
        self._boundary_validator.validate(chunks)

        # Check for large classes that should be flattened
        large_classes = self._boundary_validator.check_large_class_flatten(chunks)
        if large_classes:
            # For MVP: Just log, don't modify chunks
            # Future: Implement flatten mode that converts large classes to summary-only
            pass

    # ============================================================
    # P1: New Chunk Types (M1)
    # ============================================================

    def _build_docstring_chunks(
        self,
        class_chunks: list[Chunk],
        func_chunks: list[Chunk],
        ir_doc: "IRDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build docstring chunks from function/class docstrings.

        P1: Separates docstrings for better RAG (semantic search on docs only).

        Args:
            class_chunks: Parent class chunks
            func_chunks: Parent function chunks
            ir_doc: IR document
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of docstring chunks
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        docstring_chunks = []

        # Get all nodes with docstrings
        nodes_with_docstrings = [n for n in ir_doc.nodes if n.docstring and n.docstring.strip()]

        for node in nodes_with_docstrings:
            # Find parent chunk (class or function)
            parent_chunk = None
            if node.kind == NodeKind.CLASS:
                # Find in class_chunks
                parent_chunk = next((c for c in class_chunks if c.symbol_id == node.id), None)
            elif node.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                # Find in func_chunks
                parent_chunk = next((c for c in func_chunks if c.symbol_id == node.id), None)

            if not parent_chunk:
                continue

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="docstring", fqn=f"{node.fqn}.__doc__")
            chunk_id = self._id_gen.generate(ctx)

            # Use docstring as content
            docstring_content = node.docstring.strip()
            content_hash = self._md5_hasher(docstring_content.encode()).hexdigest()

            # Create docstring chunk
            docstring_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=parent_chunk.project_id,
                module_path=parent_chunk.module_path,
                file_path=node.file_path,
                kind="docstring",
                fqn=f"{node.fqn}.__doc__",
                start_line=node.span.start_line,  # Same as parent (approximate)
                end_line=node.span.start_line + len(docstring_content.split("\n")),
                original_start_line=node.span.start_line,
                original_end_line=node.span.start_line + len(docstring_content.split("\n")),
                content_hash=content_hash,
                parent_id=parent_chunk.chunk_id,
                children=[],  # Leaf
                language=node.language,
                symbol_visibility=parent_chunk.symbol_visibility,
                symbol_id=node.id,
                symbol_owner_id=node.id,
                summary=docstring_content[:200] if len(docstring_content) > 200 else docstring_content,
                importance=None,
                attrs={"parent_kind": node.kind.value, "docstring_length": len(docstring_content)},
            )

            # Link parent → child
            parent_chunk.children.append(chunk_id)

            docstring_chunks.append(docstring_chunk)

        record_counter("chunk_build_docstring_count", len(docstring_chunks))
        return docstring_chunks

    def _build_file_header_chunks(
        self,
        file_chunks: list[Chunk],
        ir_doc: "IRDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build file header chunks (imports + top comments + module constants).

        P1: File headers provide quick dependency understanding.

        Strategy:
        - Extract imports (from, import, using, require, etc.)
        - Include top comments (module docstrings, copyright, etc.)
        - Include module-level constants (up to first function/class)
        - Stop at first function/class definition

        Args:
            file_chunks: Parent file chunks
            ir_doc: IR document
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of file header chunks
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        header_chunks = []

        for file_chunk in file_chunks:
            if not file_chunk.file_path or not file_text:
                continue

            # Find first function/class in this file
            first_symbol_line = None
            for node in ir_doc.nodes:
                if node.file_path == file_chunk.file_path and node.kind in (
                    NodeKind.FUNCTION,
                    NodeKind.CLASS,
                    NodeKind.METHOD,
                ):
                    if first_symbol_line is None or node.span.start_line < first_symbol_line:
                        first_symbol_line = node.span.start_line

            # If no symbols, skip header chunk
            if first_symbol_line is None or first_symbol_line <= 1:
                continue

            # Extract header (line 1 to line before first symbol)
            header_end_line = first_symbol_line - 1
            header_lines = file_text[:header_end_line]

            # Skip if header is too short (< 2 lines)
            if len(header_lines) < 2:
                continue

            header_content = "\n".join(header_lines)
            content_hash = self._md5_hasher(header_content.encode()).hexdigest()

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="file_header", fqn=f"{file_chunk.fqn}.__header__")
            chunk_id = self._id_gen.generate(ctx)

            # Count imports
            import_count = sum(
                1
                for line in header_lines
                if line.strip().startswith(("import ", "from ", "using ", "require(", "#include"))
            )

            # Create file header chunk
            header_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=file_chunk.project_id,
                module_path=file_chunk.module_path,
                file_path=file_chunk.file_path,
                kind="file_header",
                fqn=f"{file_chunk.fqn}.__header__",
                start_line=1,
                end_line=header_end_line,
                original_start_line=1,
                original_end_line=header_end_line,
                content_hash=content_hash,
                parent_id=file_chunk.chunk_id,
                children=[],  # Leaf
                language=file_chunk.language,
                symbol_visibility="public",  # Headers are always public
                symbol_id=None,
                symbol_owner_id=None,
                summary=f"File header with {import_count} imports",
                importance=None,
                attrs={"import_count": import_count, "line_count": len(header_lines)},
            )

            # Link parent → child
            file_chunk.children.append(chunk_id)

            header_chunks.append(header_chunk)

        record_counter("chunk_build_file_header_count", len(header_chunks))
        return header_chunks

    def _build_skeleton_chunks(
        self,
        file_chunks: list[Chunk],
        class_chunks: list[Chunk],
        func_chunks: list[Chunk],
        ir_doc: "IRDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build skeleton chunks (file structure with signatures only).

        P1: Skeletons provide quick file structure understanding.

        Strategy:
        - Keep imports
        - Keep class/function signatures
        - Replace bodies with "..."
        - Useful for large files (RepoMap, quick navigation)

        Args:
            file_chunks: Parent file chunks
            class_chunks: Class chunks
            func_chunks: Function chunks
            ir_doc: IR document
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of skeleton chunks
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        skeleton_chunks = []

        for file_chunk in file_chunks:
            if not file_chunk.file_path or not file_text or len(file_text) < 10:
                continue

            # Get all nodes for this file
            file_nodes = [n for n in ir_doc.nodes if n.file_path == file_chunk.file_path]

            # Skip if no meaningful content
            if len(file_nodes) < 2:
                continue

            # Build skeleton content
            skeleton_lines = []
            last_line = 0

            # Sort nodes by start line
            sorted_nodes = sorted(
                [n for n in file_nodes if n.kind in (NodeKind.FUNCTION, NodeKind.CLASS, NodeKind.METHOD)],
                key=lambda n: n.span.start_line,
            )

            for node in sorted_nodes:
                # Add content before this node (imports, comments, etc.)
                before_lines = file_text[last_line : node.span.start_line - 1]
                skeleton_lines.extend(before_lines)

                # Add signature only (first line of definition)
                if node.span.start_line <= len(file_text):
                    signature_line = file_text[node.span.start_line - 1].rstrip()
                    skeleton_lines.append(signature_line)

                    # Add body placeholder
                    indent = len(signature_line) - len(signature_line.lstrip())
                    skeleton_lines.append(" " * (indent + 4) + "...")

                last_line = node.span.end_line

            # Add remaining lines (if any)
            if last_line < len(file_text):
                skeleton_lines.extend(file_text[last_line:])

            skeleton_content = "\n".join(skeleton_lines)

            # Skip if too short
            if len(skeleton_content) < 20:
                continue

            content_hash = self._md5_hasher(skeleton_content.encode()).hexdigest()

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="skeleton", fqn=f"{file_chunk.fqn}.__skeleton__")
            chunk_id = self._id_gen.generate(ctx)

            # Count symbols
            symbol_count = len(sorted_nodes)

            # Create skeleton chunk
            skeleton_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=file_chunk.project_id,
                module_path=file_chunk.module_path,
                file_path=file_chunk.file_path,
                kind="skeleton",
                fqn=f"{file_chunk.fqn}.__skeleton__",
                start_line=1,
                end_line=len(file_text),
                original_start_line=1,
                original_end_line=len(file_text),
                content_hash=content_hash,
                parent_id=file_chunk.chunk_id,
                children=[],  # Leaf
                language=file_chunk.language,
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=f"File skeleton with {symbol_count} symbols",
                importance=None,
                attrs={
                    "symbol_count": symbol_count,
                    "original_lines": len(file_text),
                    "skeleton_lines": len(skeleton_lines),
                    "compression_ratio": round(len(skeleton_lines) / len(file_text), 2) if file_text else 0,
                },
            )

            # Link parent → child
            file_chunk.children.append(chunk_id)

            skeleton_chunks.append(skeleton_chunk)

        record_counter("chunk_build_skeleton_count", len(skeleton_chunks))
        return skeleton_chunks

    def _build_usage_chunks(
        self,
        func_chunks: list[Chunk],
        ir_doc: "IRDocument",
        file_text: list[str],
        snapshot_id: str,
    ) -> list[Chunk]:
        """
        Build usage chunks from call sites.

        P2: Usage chunks show how functions are actually used in practice.

        Strategy:
        - Find CALLS edges from IR
        - Extract surrounding context (±3 lines)
        - Create usage chunk for each call site

        Args:
            func_chunks: Function chunks (to find targets)
            ir_doc: IR document
            file_text: Source code lines
            snapshot_id: Git commit hash or timestamp

        Returns:
            List of usage chunks
        """
        from src.contexts.code_foundation.infrastructure.ir.models import EdgeKind

        usage_chunks = []

        # Get all CALLS edges
        call_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.CALLS and e.span is not None]

        for edge in call_edges:
            # Find target function chunk
            target_chunk = next((c for c in func_chunks if c.symbol_id == edge.target_id), None)
            if not target_chunk:
                continue

            # Extract call site code (±3 lines context)
            call_line = edge.span.start_line
            context_before = 3
            context_after = 3

            start_line = max(1, call_line - context_before)
            end_line = min(len(file_text), call_line + context_after)

            usage_code = self._extract_code_span(file_text, start_line, end_line)
            content_hash = self._md5_hasher(usage_code.encode()).hexdigest()

            # Generate chunk ID
            usage_fqn = f"{target_chunk.fqn}.__usage__{edge.source_id}"
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="usage", fqn=usage_fqn)
            chunk_id = self._id_gen.generate(ctx)

            # Find source node (caller)
            source_node = next((n for n in ir_doc.nodes if n.id == edge.source_id), None)
            source_fqn = source_node.fqn if source_node else edge.source_id

            # Create usage chunk
            usage_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=ir_doc.repo_id,
                snapshot_id=snapshot_id,
                project_id=target_chunk.project_id,
                module_path=target_chunk.module_path,
                file_path=source_node.file_path if source_node else target_chunk.file_path,  # Usage는 호출하는 쪽 파일
                kind="usage",
                fqn=usage_fqn,
                start_line=start_line,
                end_line=end_line,
                original_start_line=start_line,
                original_end_line=end_line,
                content_hash=content_hash,
                parent_id=target_chunk.chunk_id,
                children=[],  # Leaf
                language=target_chunk.language,
                symbol_visibility="public",  # Usage is always visible
                symbol_id=edge.target_id,  # Target function
                symbol_owner_id=edge.target_id,
                summary=f"Usage of {target_chunk.fqn} in {source_fqn}",
                importance=None,
                attrs={
                    "caller": source_fqn,
                    "callee": target_chunk.fqn,
                    "call_line": call_line,
                    "context_lines": context_after + context_before + 1,
                },
            )

            # Link parent → child
            target_chunk.children.append(chunk_id)

            usage_chunks.append(usage_chunk)

        record_counter("chunk_build_usage_count", len(usage_chunks))
        return usage_chunks
