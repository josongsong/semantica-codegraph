"""
Chunk Hierarchy Builder

Builds 6-level chunk hierarchy from IR + Graph:
    Repo → Project → Module → File → Class → Function
"""

from typing import TYPE_CHECKING

from .boundary import ChunkBoundaryValidator
from .builder_graphfirst import map_graph_kind_to_chunk_kind
from .id_generator import ChunkIdContext, ChunkIdGenerator
from .mapping import ChunkGraphMapper, ChunkMapper
from .models import Chunk, ChunkToGraph, ChunkToIR

if TYPE_CHECKING:
    from ..graph.models import GraphDocument
    from ..ir.models import IRDocument, Node


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

    def build(
        self,
        repo_id: str,
        ir_doc: "IRDocument",
        graph_doc: "GraphDocument",
        file_text: list[str],
        repo_config: dict,
        snapshot_id: str | None = None,
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

        Returns:
            Tuple of (chunks, chunk_to_ir, chunk_to_graph)
        """
        self._chunks = []
        snapshot_id = snapshot_id or "default"

        # 1. Build structural hierarchy: Repo → Project → Module → File
        repo_chunk = self._build_repo_chunk(repo_id, repo_config, snapshot_id)
        project_chunks = self._build_project_chunks(repo_chunk, repo_config, snapshot_id)
        self._project_chunks = project_chunks  # Store for reuse in _build_file_chunks
        module_chunks = self._build_module_chunks(project_chunks, ir_doc, snapshot_id)
        file_chunks = self._build_file_chunks(module_chunks, ir_doc, file_text, snapshot_id)

        # 2. Build symbol hierarchy: Class → Function
        # Graph-First: Pass graph_doc to use Graph as single source of truth
        class_chunks = self._build_class_chunks(file_chunks, ir_doc, graph_doc, file_text, snapshot_id)
        func_chunks = self._build_function_chunks(class_chunks, file_chunks, ir_doc, graph_doc, file_text, snapshot_id)

        # Collect all chunks
        chunks = [
            repo_chunk,
            *project_chunks,
            *module_chunks,
            *file_chunks,
            *class_chunks,
            *func_chunks,
        ]

        # 4. Build mappings & validate
        chunk_to_ir, chunk_to_graph = self._build_mappings(chunks, ir_doc, graph_doc)
        self._validate_boundaries(chunks)

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
        from ..ir.models import NodeKind

        file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]
        if not file_nodes:
            return []

        # For MVP: Single file processing
        file_node = file_nodes[0]
        file_path = file_node.file_path

        # Extract module hierarchy from path
        # Example: "backend/search/retriever.py" → ["backend", "search"]
        parts = file_path.split("/")
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
        from ..ir.models import NodeKind

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

            # Build FQN from file path
            # Example: "backend/search/retriever.py" → "backend.search.retriever"
            file_path = file_node.file_path
            fqn = file_path.replace("/", ".").replace(".py", "")

            # Generate chunk ID
            ctx = ChunkIdContext(repo_id=ir_doc.repo_id, kind="file", fqn=fqn)
            chunk_id = self._id_gen.generate(ctx)

            # Calculate content hash (simple hash for MVP)
            import hashlib

            content_hash = hashlib.md5("".join(file_text).encode()).hexdigest()

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
        from ..ir.models import NodeKind

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

            # Extract class code for content hash
            class_code = self._extract_code_span(file_text, class_node.span.start_line, class_node.span.end_line)
            import hashlib

            content_hash = hashlib.md5(class_code.encode()).hexdigest()

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
                symbol_visibility="public",  # TODO: Extract from attrs
                symbol_id=class_node.id,
                symbol_owner_id=class_node.id,
                summary=None,
                importance=None,
                attrs={"role": class_node.role} if class_node.role else {},
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
        from ..ir.models import NodeKind

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

            # Extract function code for content hash
            func_code = self._extract_code_span(file_text, func_node.span.start_line, func_node.span.end_line)
            import hashlib

            content_hash = hashlib.md5(func_code.encode()).hexdigest()

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
                symbol_visibility="public",  # TODO: Extract from attrs
                symbol_id=func_node.id,
                symbol_owner_id=func_node.id,
                summary=None,
                importance=None,
                attrs={},
            )

            # Link parent → child
            parent_chunk.children.append(chunk_id)

            func_chunks.append(func_chunk)

        return func_chunks

    # ============================================================
    # Helpers
    # ============================================================

    def _find_parent_file_chunk(self, file_chunks: list[Chunk], node: "Node") -> Chunk | None:
        """Find the file chunk containing this node."""
        for file_chunk in file_chunks:
            if file_chunk.file_path == node.file_path:
                return file_chunk
        return None

    def _find_parent_class_chunk(self, class_chunks: list[Chunk], node: "Node") -> Chunk | None:
        """Find the class chunk containing this node (for methods)."""
        for class_chunk in class_chunks:
            if (
                class_chunk.file_path == node.file_path
                and class_chunk.start_line is not None
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

    def _extract_code_span(self, file_text: list[str], start_line: int, end_line: int) -> str:
        """Extract code from file text for a given line range."""
        # Lines are 1-indexed in span, but list is 0-indexed
        return "\n".join(file_text[start_line - 1 : end_line])

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
