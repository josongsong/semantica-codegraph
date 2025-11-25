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

from src.foundation.chunk.models import Chunk
from src.repomap.id_strategy import RepoMapIdGenerator
from src.repomap.models import RepoMapMetrics, RepoMapNode


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

    def build(self, chunks: list[Chunk]) -> list[RepoMapNode]:
        """
        Build RepoMap tree from chunks.

        Args:
            chunks: List of chunks (all levels)

        Returns:
            List of RepoMapNodes (flat list, parent-child via IDs)
        """
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
                metrics=metrics,
                language=chunk.language,
            )
            self.nodes[node_id] = node

            # Update parent's children list
            if parent_id and parent_id in self.nodes:
                if node_id not in self.nodes[parent_id].children_ids:
                    self.nodes[parent_id].children_ids.append(node_id)

    def _find_parent_id(self, chunk: Chunk, root_id: str) -> str | None:
        """Find parent RepoMapNode ID for a chunk."""
        # If chunk has parent_id, try to find corresponding RepoMapNode
        if chunk.parent_id:
            # Search for node with matching chunk_id
            for node_id, node in self.nodes.items():
                if chunk.parent_id in node.chunk_ids:
                    return node_id

        # Fallback: determine parent by kind and path
        if chunk.kind == "file":
            # Parent is directory
            if chunk.file_path:
                parent_path = str(Path(chunk.file_path).parent)
                if parent_path == ".":
                    return root_id
                return self.id_gen.generate_dir(self.repo_id, self.snapshot_id, parent_path)

        elif chunk.kind in ["class", "function"]:
            # Parent is file or class
            if chunk.file_path:
                return self.id_gen.generate_file(self.repo_id, self.snapshot_id, chunk.file_path)

        # Default: root
        return root_id

    def _calculate_depth(self, chunk: Chunk) -> int:
        """Calculate tree depth for a chunk."""
        depth_map = {
            "repo": 0,
            "project": 1,
            "module": 2,
            "file": 3,
            "class": 4,
            "function": 5,
        }

        base_depth = depth_map.get(chunk.kind, 3)

        # Adjust for file path depth
        if chunk.file_path:
            path_depth = chunk.file_path.count(os.sep)
            return base_depth + path_depth

        return base_depth

    def _get_display_name(self, chunk: Chunk) -> str:
        """Get display name for a chunk."""
        # Use last part of FQN
        if chunk.fqn:
            return chunk.fqn.split(".")[-1]

        # Use filename
        if chunk.file_path:
            return os.path.basename(chunk.file_path)

        # Fallback
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
