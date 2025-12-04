"""
RepoMap Tree Builder

Builds hierarchical RepoMap tree from Chunk layer.

Process:
1. Read Chunk hierarchy (repo → project → module → file → class → function)
2. Generate intermediate directory nodes (not in Chunk layer)
3. Create RepoMapNode for each level
4. Compute basic metrics (LOC, symbol count)
5. Build parent-child relationships
"""

import os
from collections import defaultdict
from pathlib import Path

from src.contexts.code_foundation.infrastructure.chunk.models import Chunk
from src.contexts.repo_structure.infrastructure.id_strategy import RepoMapIdGenerator
from src.contexts.repo_structure.infrastructure.models import RepoMapMetrics, RepoMapNode


class RepoMapTreeBuilder:
    """
    Build RepoMap tree from Chunk hierarchy.

    The tree follows this structure:
        Repo (root)
        ├── Dir (src/)
        │   ├── Dir (src/indexing/)
        │   │   ├── File (src/indexing/builder.py)
        │   │   │   ├── Class (IndexBuilder)
        │   │   │   │   ├── Function (build)
        │   │   │   │   └── Function (validate)
        │   │   │   └── Function (helper_func)
    """

    def __init__(self, repo_id: str, snapshot_id: str):
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.nodes: dict[str, RepoMapNode] = {}
        self.id_gen = RepoMapIdGenerator()
        # Reverse index: chunk_id -> node_id for O(1) parent lookup
        self.chunk_to_node_id: dict[str, str] = {}
        # FQN index: (kind, fqn) -> node_id for O(1) class lookup by FQN
        self.fqn_to_node_id: dict[tuple[str, str], str] = {}

    def build(
        self,
        chunks: list[Chunk],
        chunk_to_graph: dict[str, set[str]] | None = None,
    ) -> list[RepoMapNode]:
        """
        Build RepoMap tree from chunks.

        Args:
            chunks: List of chunks (all levels)
            chunk_to_graph: Mapping from chunk_id to graph_node_ids for PageRank

        Returns:
            List of RepoMapNodes (flat list, parent-child via IDs)
        """
        self.chunk_to_graph = chunk_to_graph or {}

        # Step 1: Create repo root
        self._create_repo_root(chunks)

        # Step 2: Group chunks by kind
        chunks_by_kind = self._group_chunks_by_kind(chunks)

        # Step 3: Build directory structure from file paths
        file_chunks = chunks_by_kind.get("file", [])
        self._build_directory_nodes(file_chunks)

        # Step 4: Create nodes for chunks
        self._create_chunk_nodes(chunks)

        # Step 5: Aggregate metrics bottom-up
        self._aggregate_metrics()

        return list(self.nodes.values())

    def _create_repo_root(self, chunks: list[Chunk]) -> None:
        """Create root repository node."""
        repo_chunk = next((c for c in chunks if c.kind == "repo"), None)

        root_id = self.id_gen.generate_repo_root(self.repo_id, self.snapshot_id)
        root_node = RepoMapNode(
            id=root_id,
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            kind="repo",
            name=self.repo_id,
            path=None,
            fqn=None,
            parent_id=None,
            depth=0,
            chunk_ids=[repo_chunk.chunk_id] if repo_chunk else [],
        )
        self.nodes[root_id] = root_node

    def _group_chunks_by_kind(self, chunks: list[Chunk]) -> dict[str, list[Chunk]]:
        """Group chunks by kind."""
        grouped: dict[str, list[Chunk]] = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.kind].append(chunk)
        return grouped

    def _build_directory_nodes(self, file_chunks: list[Chunk]) -> None:
        """
        Create directory nodes from file paths.

        Intermediate directories not present in Chunk layer are created here.
        """
        # Collect all directory paths
        dir_paths: set[str] = set()
        for file_chunk in file_chunks:
            if not file_chunk.file_path:
                continue

            # Get all parent directories
            path = Path(file_chunk.file_path)
            for parent in path.parents:
                if str(parent) != ".":
                    dir_paths.add(str(parent))

        # Sort by depth (shallowest first)
        sorted_dirs = sorted(dir_paths, key=lambda p: p.count(os.sep))

        root_id = self.id_gen.generate_repo_root(self.repo_id, self.snapshot_id)

        for dir_path in sorted_dirs:
            dir_id = self.id_gen.generate_dir(self.repo_id, self.snapshot_id, dir_path)

            # Find parent
            parent_path = str(Path(dir_path).parent)
            if parent_path == ".":
                parent_id = root_id
            else:
                parent_id = self.id_gen.generate_dir(self.repo_id, self.snapshot_id, parent_path)

            # Calculate depth
            depth = dir_path.count(os.sep) + 1

            dir_node = RepoMapNode(
                id=dir_id,
                repo_id=self.repo_id,
                snapshot_id=self.snapshot_id,
                kind="dir",
                name=os.path.basename(dir_path),
                path=dir_path,
                parent_id=parent_id,
                depth=depth,
            )
            self.nodes[dir_id] = dir_node

            # Update parent's children list
            if parent_id in self.nodes:
                if dir_id not in self.nodes[parent_id].children_ids:
                    self.nodes[parent_id].children_ids.append(dir_id)

    def _create_chunk_nodes(self, chunks: list[Chunk]) -> None:
        """
        Create RepoMapNode for each chunk.

        Maps chunk hierarchy to RepoMap hierarchy.
        """
        # Sort by depth: repo → project → module → file → class → function
        kind_order = ["repo", "project", "module", "file", "class", "function"]
        sorted_chunks = sorted(chunks, key=lambda c: kind_order.index(c.kind) if c.kind in kind_order else 99)

        root_id = self.id_gen.generate_repo_root(self.repo_id, self.snapshot_id)

        for chunk in sorted_chunks:
            # Skip repo (already created)
            if chunk.kind == "repo":
                continue

            # Determine node kind and identifier
            if chunk.kind == "file":
                node_kind = "file"
                identifier = chunk.file_path or chunk.fqn
            elif chunk.kind in ["class", "function"]:
                node_kind = chunk.kind
                identifier = chunk.fqn
            elif chunk.kind == "module":
                node_kind = "module"
                identifier = chunk.module_path or chunk.fqn
            elif chunk.kind == "project":
                node_kind = "project"
                identifier = chunk.project_id or chunk.fqn
            else:
                # Skip unknown kinds
                continue

            if not identifier:
                continue

            # Generate node ID
            node_id = self.id_gen.generate_symbol(self.repo_id, self.snapshot_id, identifier, kind=node_kind)

            # Find parent ID
            parent_id = self._find_parent_id(chunk, root_id)

            # Calculate depth
            depth = self._calculate_depth(chunk)

            # Initial metrics from chunk
            metrics = RepoMapMetrics(
                loc=self._estimate_loc(chunk),
                symbol_count=1 if chunk.kind in ["class", "function"] else 0,
            )

            # Get graph_node_ids for this chunk
            graph_node_ids = list(self.chunk_to_graph.get(chunk.chunk_id, set()))

            # Create node
            node = RepoMapNode(
                id=node_id,
                repo_id=self.repo_id,
                snapshot_id=self.snapshot_id,
                kind=node_kind,
                name=self._get_display_name(chunk),
                path=chunk.file_path,
                fqn=chunk.fqn,
                parent_id=parent_id,
                depth=depth,
                chunk_ids=[chunk.chunk_id],
                graph_node_ids=graph_node_ids,
                metrics=metrics,
                language=chunk.language,
            )
            self.nodes[node_id] = node

            # Update reverse index for O(1) parent lookup
            self.chunk_to_node_id[chunk.chunk_id] = node_id

            # Update FQN index for O(1) class/function lookup
            if chunk.fqn:
                self.fqn_to_node_id[(node_kind, chunk.fqn)] = node_id

            # Update parent's children list
            if parent_id and parent_id in self.nodes:
                if node_id not in self.nodes[parent_id].children_ids:
                    self.nodes[parent_id].children_ids.append(node_id)

    def _find_parent_id(self, chunk: Chunk, root_id: str) -> str | None:
        """
        Find parent RepoMapNode ID for a chunk.

        Uses O(1) reverse index lookup for performance.
        """
        # If chunk has parent_id, use reverse index for O(1) lookup
        if chunk.parent_id:
            parent_node_id = self.chunk_to_node_id.get(chunk.parent_id)
            if parent_node_id:
                return parent_node_id

        # Fallback: determine parent by kind and path
        if chunk.kind == "file":
            # Parent is directory
            if chunk.file_path:
                parent_path = str(Path(chunk.file_path).parent)
                if parent_path == ".":
                    return root_id
                return self.id_gen.generate_dir(self.repo_id, self.snapshot_id, parent_path)

        elif chunk.kind == "function":
            # Functions can be nested in classes or directly in files
            # First, try to find parent class from chunk.parent_id
            if chunk.parent_id:
                parent_node_id = self.chunk_to_node_id.get(chunk.parent_id)
                if parent_node_id and self.nodes[parent_node_id].kind == "class":
                    return parent_node_id

            # If no class parent, check if FQN indicates class membership
            if chunk.fqn and "." in chunk.fqn:
                # Try to find class by FQN (e.g., "module.ClassName.method_name")
                parts = chunk.fqn.rsplit(".", 1)
                if len(parts) == 2:
                    potential_class_fqn = parts[0]
                    # O(1) lookup using FQN index
                    class_node_id = self.fqn_to_node_id.get(("class", potential_class_fqn))
                    if class_node_id:
                        return class_node_id

            # Fall back to file parent
            if chunk.file_path:
                return self.id_gen.generate_file(self.repo_id, self.snapshot_id, chunk.file_path)

        elif chunk.kind == "class":
            # Classes can be nested in other classes or in files
            if chunk.parent_id:
                parent_node_id = self.chunk_to_node_id.get(chunk.parent_id)
                if parent_node_id:
                    return parent_node_id

            # Fall back to file parent
            if chunk.file_path:
                return self.id_gen.generate_file(self.repo_id, self.snapshot_id, chunk.file_path)

        # Default: root
        return root_id

    def _calculate_depth(self, chunk: Chunk) -> int:
        """
        Calculate tree depth for a chunk.

        Depth is calculated as parent_depth + 1 for proper parent-child alignment.
        """
        # Repo root is always depth 0
        if chunk.kind == "repo":
            return 0

        # For all other nodes, calculate depth based on their logical parent
        root_id = self.id_gen.generate_repo_root(self.repo_id, self.snapshot_id)
        parent_id = self._find_parent_id(chunk, root_id)

        # If parent exists in nodes, use parent_depth + 1
        if parent_id and parent_id in self.nodes:
            return self.nodes[parent_id].depth + 1

        # Fallback: calculate based on path or kind
        if chunk.file_path:
            # Count directory separators as depth
            return chunk.file_path.count(os.sep) + 1

        # Default depth by kind (shouldn't reach here normally)
        depth_map = {
            "project": 1,
            "module": 2,
            "file": 3,
            "class": 4,
            "function": 5,
        }
        return depth_map.get(chunk.kind, 3)

    def _get_display_name(self, chunk: Chunk) -> str:
        """Get display name for a chunk with improved fallback logic."""
        # Priority 1: Use last part of FQN (most specific)
        if chunk.fqn:
            return chunk.fqn.split(".")[-1]

        # Priority 2: Use chunk.name if available
        if hasattr(chunk, "name") and chunk.name:
            return chunk.name

        # Priority 3: Use filename
        if chunk.file_path:
            return os.path.basename(chunk.file_path)

        # Priority 4: Use module_path if available
        if hasattr(chunk, "module_path") and chunk.module_path:
            return chunk.module_path.split(".")[-1]

        # Final fallback: generate from chunk_id
        return f"{chunk.kind}_{chunk.chunk_id.split(':')[-1][:8]}"

    def _estimate_loc(self, chunk: Chunk) -> int:
        """Estimate lines of code for a chunk."""
        if chunk.start_line is not None and chunk.end_line is not None:
            return max(0, chunk.end_line - chunk.start_line + 1)
        return 0

    def _aggregate_metrics(self) -> None:
        """
        Aggregate metrics bottom-up (leaf → root) in single pass.

        Strategy:
        1. Sort nodes by depth descending (deepest first)
        2. Single pass: each node contributes to parent once
        3. No recursion, no duplicate computation

        Time complexity: O(N log N) for sort + O(N) for aggregation = O(N log N)
        Previous complexity: O(N × H) where H = tree height
        """
        # Sort nodes by depth descending (leaf → root order)
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: n.depth, reverse=True)  # Deepest first (leaf nodes)

        # Single pass: aggregate from children to parents
        for node in sorted_nodes:
            if not node.parent_id:
                continue  # Skip root (no parent)

            parent = self.nodes.get(node.parent_id)
            if not parent:
                continue

            # Aggregate metrics to parent (happens exactly once per node)
            parent.metrics.loc += node.metrics.loc
            parent.metrics.symbol_count += node.metrics.symbol_count
