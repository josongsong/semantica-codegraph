"""
Graph Merger

Merges base graph with overlay graph to create a unified view.
"""

from typing import Dict, Set, Optional, Tuple
from collections import defaultdict

from src.common.observability import get_logger
from src.infra.graph.memgraph import MemgraphGraphStore
from .models import (
    OverlaySnapshot,
    MergedSnapshot,
    SymbolConflict,
)
from .conflict_resolver import ConflictResolver

logger = get_logger(__name__)


class GraphMerger:
    """
    Merge base graph + overlay graph

    Strategy:
    1. Overlay symbols always override base symbols
    2. Edges are updated to point to overlay symbols
    3. Conflicts are tracked but resolved in favor of overlay
    """

    def __init__(
        self,
        graph_store: Optional[MemgraphGraphStore] = None,  # Memgraph Graph Store
        conflict_resolver: Optional[ConflictResolver] = None,
    ):
        self.graph_store = graph_store or MemgraphGraphStore()
        self.conflict_resolver = conflict_resolver or ConflictResolver()

    async def merge_graphs(
        self, base_snapshot_id: str, overlay: OverlaySnapshot, base_ir_docs: Dict[str, dict]
    ) -> MergedSnapshot:
        """
        Merge base + overlay to create unified snapshot

        Args:
            base_snapshot_id: Base snapshot ID
            overlay: Overlay snapshot
            base_ir_docs: Base IR documents

        Returns:
            MergedSnapshot with unified view

        Process:
        1. Load base graph
        2. Apply overlay changes
        3. Resolve conflicts
        4. Rebuild affected edges
        5. Create merged snapshot
        """
        logger.info(
            "merging_graphs",
            base_snapshot_id=base_snapshot_id,
            overlay_id=overlay.snapshot_id,
            num_overlay_files=len(overlay.uncommitted_files),
        )

        # Check cache
        if overlay.is_cache_valid():
            cached = overlay.get_cached_snapshot()
            if cached:
                logger.info("using_cached_merged_snapshot")
                return MergedSnapshot(**cached)

        # Create merged snapshot
        merged = MergedSnapshot(
            snapshot_id=f"merged_{overlay.snapshot_id}",
            base_snapshot_id=base_snapshot_id,
            overlay_snapshot_id=overlay.snapshot_id,
            repo_id=overlay.repo_id,
        )

        # Step 1: Merge IR documents (overlay priority)
        merged.ir_documents = self._merge_ir_documents(base_ir_docs, overlay.overlay_ir_docs)

        # Step 2: Build unified symbol index
        merged.symbol_index = self._build_symbol_index(merged.ir_documents)

        # Step 3: Detect and resolve conflicts
        conflicts = self._detect_conflicts(base_ir_docs, overlay.overlay_ir_docs, merged.symbol_index)

        for conflict in conflicts:
            resolved = self.conflict_resolver.resolve(conflict)
            merged.conflicts.append(resolved)

        # Step 4: Merge call graph
        merged.call_graph_edges = await self._merge_call_graph(base_snapshot_id, overlay, merged.symbol_index)

        # Step 5: Merge import graph
        merged.import_graph_edges = await self._merge_import_graph(base_snapshot_id, overlay, merged.symbol_index)

        # Cache result
        overlay.cache_merged_snapshot(merged.__dict__)

        logger.info(
            "graphs_merged",
            num_ir_docs=len(merged.ir_documents),
            num_symbols=len(merged.symbol_index),
            num_conflicts=len(merged.conflicts),
            num_call_edges=len(merged.call_graph_edges),
            num_import_edges=len(merged.import_graph_edges),
        )

        return merged

    def _merge_ir_documents(self, base_docs: Dict[str, dict], overlay_docs: Dict[str, dict]) -> Dict[str, dict]:
        """
        Merge IR documents (overlay priority)

        Overlay documents completely override base documents.
        """
        merged = base_docs.copy()
        merged.update(overlay_docs)  # Overlay wins
        return merged

    def _build_symbol_index(self, ir_documents: Dict[str, dict]) -> Dict[str, dict]:
        """
        Build unified symbol index from IR documents

        Returns:
            {symbol_id: symbol_dict}
        """
        symbol_index = {}

        for file_path, ir_doc in ir_documents.items():
            for symbol in ir_doc.get("symbols", []):
                symbol_id = symbol.get("id")
                if symbol_id:
                    # Add file path to symbol
                    symbol["file"] = file_path
                    symbol_index[symbol_id] = symbol

        return symbol_index

    def _detect_conflicts(
        self, base_docs: Dict[str, dict], overlay_docs: Dict[str, dict], merged_symbols: Dict[str, dict]
    ) -> list[SymbolConflict]:
        """
        Detect conflicts between base and overlay

        Conflicts occur when:
        - Symbol signature changed
        - Symbol deleted
        - Symbol moved to different file
        """
        conflicts = []

        # Build base symbol index
        base_symbols = {}
        for file_path, ir_doc in base_docs.items():
            for symbol in ir_doc.get("symbols", []):
                symbol_id = symbol.get("id")
                if symbol_id:
                    base_symbols[symbol_id] = symbol

        # Build overlay symbol index
        overlay_symbols = {}
        for file_path, ir_doc in overlay_docs.items():
            for symbol in ir_doc.get("symbols", []):
                symbol_id = symbol.get("id")
                if symbol_id:
                    overlay_symbols[symbol_id] = symbol

        # Check for conflicts
        all_symbols = set(base_symbols.keys()) | set(overlay_symbols.keys())

        for symbol_id in all_symbols:
            base_sym = base_symbols.get(symbol_id)
            overlay_sym = overlay_symbols.get(symbol_id)

            if base_sym and not overlay_sym:
                # Symbol deleted in overlay
                conflicts.append(
                    SymbolConflict(
                        symbol_id=symbol_id,
                        base_signature=base_sym.get("signature"),
                        base_location=(
                            base_sym.get("file"),
                            base_sym.get("range", {}).get("start", {}).get("line"),
                            base_sym.get("range", {}).get("start", {}).get("character"),
                        ),
                        overlay_signature=None,
                        overlay_location=None,
                        conflict_type="deletion",
                        resolution="overlay_wins",
                    )
                )

            elif overlay_sym and not base_sym:
                # Symbol added in overlay (not a conflict, just info)
                pass

            elif base_sym and overlay_sym:
                # Check for signature change
                if base_sym.get("signature") != overlay_sym.get("signature"):
                    conflicts.append(
                        SymbolConflict(
                            symbol_id=symbol_id,
                            base_signature=base_sym.get("signature"),
                            base_location=(
                                base_sym.get("file"),
                                base_sym.get("range", {}).get("start", {}).get("line"),
                                base_sym.get("range", {}).get("start", {}).get("character"),
                            ),
                            overlay_signature=overlay_sym.get("signature"),
                            overlay_location=(
                                overlay_sym.get("file"),
                                overlay_sym.get("range", {}).get("start", {}).get("line"),
                                overlay_sym.get("range", {}).get("start", {}).get("character"),
                            ),
                            conflict_type="signature_change",
                            resolution="overlay_wins",
                        )
                    )

        return conflicts

    async def _merge_call_graph(
        self, base_snapshot_id: str, overlay: OverlaySnapshot, merged_symbols: Dict[str, dict]
    ) -> Set[Tuple[str, str]]:
        """
        Merge call graph edges

        Strategy:
        1. Load base call graph edges
        2. Remove edges involving affected symbols
        3. Add new edges from overlay IR
        4. Return merged edges
        """
        merged_edges = set()

        # Load base call graph
        try:
            base_edges = await self._load_base_call_graph(base_snapshot_id, overlay.repo_id)

            # Filter out edges involving affected symbols
            for caller, callee in base_edges:
                if caller not in overlay.affected_symbols and callee not in overlay.affected_symbols:
                    # Keep unchanged edge
                    merged_edges.add((caller, callee))

        except Exception as e:
            logger.warning("failed_to_load_base_call_graph", error=str(e))

        # Add overlay call graph edges
        for file_path, ir_doc in overlay.overlay_ir_docs.items():
            for symbol in ir_doc.get("symbols", []):
                caller_id = symbol.get("id")
                if not caller_id:
                    continue

                # Extract calls from symbol
                for call in symbol.get("calls", []):
                    callee_id = call.get("target_id")
                    if callee_id:
                        merged_edges.add((caller_id, callee_id))

        return merged_edges

    async def _merge_import_graph(
        self, base_snapshot_id: str, overlay: OverlaySnapshot, merged_symbols: Dict[str, dict]
    ) -> Set[Tuple[str, str]]:
        """
        Merge import graph edges

        Similar to call graph merging
        """
        merged_edges = set()

        # Load base import graph
        try:
            base_edges = await self._load_base_import_graph(base_snapshot_id, overlay.repo_id)

            # Filter out edges involving overlay files
            overlay_files = set(overlay.uncommitted_files.keys())
            for importer, imported in base_edges:
                if importer not in overlay_files:
                    # Keep unchanged edge
                    merged_edges.add((importer, imported))

        except Exception as e:
            logger.warning("failed_to_load_base_import_graph", error=str(e))

        # Add overlay import edges
        for file_path, ir_doc in overlay.overlay_ir_docs.items():
            for imp in ir_doc.get("imports", []):
                imported_module = imp.get("module")
                if imported_module:
                    merged_edges.add((file_path, imported_module))

        return merged_edges

    async def _load_base_call_graph(self, snapshot_id: str, repo_id: str) -> Set[Tuple[str, str]]:
        """Load call graph edges from base snapshot"""
        query = f"""
        MATCH (caller:Symbol)-[:CALLS]->(callee:Symbol)
        WHERE caller.repo_id = '{repo_id}' AND caller.snapshot_id = '{snapshot_id}'
        RETURN caller.id as caller_id, callee.id as callee_id
        """

        results = await self.graph_store.execute_query(query)
        return {(r["caller_id"], r["callee_id"]) for r in results}

    async def _load_base_import_graph(self, snapshot_id: str, repo_id: str) -> Set[Tuple[str, str]]:
        """Load import graph edges from base snapshot"""
        query = f"""
        MATCH (file:File)-[:IMPORTS]->(module:Module)
        WHERE file.repo_id = '{repo_id}' AND file.snapshot_id = '{snapshot_id}'
        RETURN file.path as importer, module.name as imported
        """

        results = await self.graph_store.execute_query(query)
        return {(r["importer"], r["imported"]) for r in results}
