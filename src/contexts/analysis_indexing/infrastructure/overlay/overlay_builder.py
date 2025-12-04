"""
Overlay IR Builder

Builds IR from uncommitted files and computes delta against base.
"""

import hashlib
from typing import Dict, Set, Optional
from pathlib import Path
from datetime import datetime

from src.infra.observability import get_logger
from .models import (
    OverlaySnapshot,
    UncommittedFile,
    OverlayConfig,
)

logger = get_logger(__name__)


class OverlayIRBuilder:
    """
    Build IR from uncommitted changes

    This is the core component that enables real-time code intelligence
    on uncommitted changes.
    """

    def __init__(
        self,
        ir_builder,  # BaseIRBuilder from code_foundation
        config: Optional[OverlayConfig] = None,
    ):
        self.ir_builder = ir_builder
        self.config = config or OverlayConfig()

    async def build_overlay(
        self,
        base_snapshot_id: str,
        repo_id: str,
        uncommitted_files: Dict[str, str],  # path -> content
        base_ir_docs: Optional[Dict[str, dict]] = None,
    ) -> OverlaySnapshot:
        """
        Build overlay snapshot from uncommitted files

        Args:
            base_snapshot_id: Base committed snapshot ID
            repo_id: Repository ID
            uncommitted_files: Uncommitted file contents {path: content}
            base_ir_docs: Base IR documents (for delta computation)

        Returns:
            OverlaySnapshot with IR for uncommitted changes

        Process:
        1. Parse uncommitted files to IR
        2. Compute delta vs base IR
        3. Identify affected symbols
        4. Build overlay snapshot
        """
        logger.info("building_overlay", base_snapshot_id=base_snapshot_id, num_uncommitted=len(uncommitted_files))

        # Validate
        if len(uncommitted_files) > self.config.max_overlay_files:
            logger.warning(
                "too_many_uncommitted_files", count=len(uncommitted_files), max=self.config.max_overlay_files
            )
            # Truncate to most recently modified
            uncommitted_files = dict(list(uncommitted_files.items())[: self.config.max_overlay_files])

        # Create overlay snapshot
        overlay = OverlaySnapshot(
            snapshot_id=self._generate_overlay_id(base_snapshot_id, uncommitted_files),
            base_snapshot_id=base_snapshot_id,
            repo_id=repo_id,
        )

        # Process each uncommitted file
        for file_path, content in uncommitted_files.items():
            try:
                await self._process_uncommitted_file(overlay, file_path, content, base_ir_docs)
            except Exception as e:
                logger.error("failed_to_process_uncommitted_file", file_path=file_path, error=str(e))
                # Continue with other files

        logger.info(
            "overlay_built",
            snapshot_id=overlay.snapshot_id,
            num_ir_docs=len(overlay.overlay_ir_docs),
            num_affected_symbols=len(overlay.affected_symbols),
        )

        return overlay

    async def _process_uncommitted_file(
        self, overlay: OverlaySnapshot, file_path: str, content: str, base_ir_docs: Optional[Dict[str, dict]]
    ):
        """Process single uncommitted file"""

        # Compute content hash
        content_hash = self._compute_hash(content)

        # Create UncommittedFile
        uncommitted_file = UncommittedFile(
            file_path=file_path,
            content=content,
            timestamp=datetime.utcnow(),
            content_hash=content_hash,
            is_new=(base_ir_docs is None or file_path not in base_ir_docs),
        )

        overlay.add_uncommitted_file(uncommitted_file)

        # Parse to IR
        try:
            ir_doc = await self.ir_builder.build_file_ir(file_path=file_path, content=content)

            overlay.overlay_ir_docs[file_path] = ir_doc

            # Compute delta if base exists
            if base_ir_docs and file_path in base_ir_docs:
                affected = self._compute_affected_symbols(base_ir_docs[file_path], ir_doc)
                for symbol in affected:
                    overlay.mark_affected_symbol(symbol)
            else:
                # New file → all symbols are new
                if "symbols" in ir_doc:
                    for symbol in ir_doc["symbols"]:
                        overlay.mark_affected_symbol(symbol.get("id", ""))

        except Exception as e:
            logger.error("ir_build_failed", file_path=file_path, error=str(e))
            raise

    def _compute_affected_symbols(self, base_ir: dict, overlay_ir: dict) -> Set[str]:
        """
        Compute affected symbols by comparing base vs overlay IR

        A symbol is affected if:
        - Signature changed
        - Body changed
        - Deleted
        - New symbol added
        """
        affected = set()

        base_symbols = {s["id"]: s for s in base_ir.get("symbols", [])}
        overlay_symbols = {s["id"]: s for s in overlay_ir.get("symbols", [])}

        # Deleted symbols
        deleted = set(base_symbols.keys()) - set(overlay_symbols.keys())
        affected.update(deleted)

        # New symbols
        new = set(overlay_symbols.keys()) - set(base_symbols.keys())
        affected.update(new)

        # Modified symbols
        for symbol_id in set(base_symbols.keys()) & set(overlay_symbols.keys()):
            base_sym = base_symbols[symbol_id]
            overlay_sym = overlay_symbols[symbol_id]

            # Check signature
            if base_sym.get("signature") != overlay_sym.get("signature"):
                affected.add(symbol_id)
                logger.debug(
                    "signature_changed",
                    symbol_id=symbol_id,
                    old=base_sym.get("signature"),
                    new=overlay_sym.get("signature"),
                )

            # Check body (content hash)
            elif self._symbol_body_changed(base_sym, overlay_sym):
                affected.add(symbol_id)
                logger.debug("body_changed", symbol_id=symbol_id)

        return affected

    def _symbol_body_changed(self, base_sym: dict, overlay_sym: dict) -> bool:
        """Check if symbol body changed"""
        base_range = base_sym.get("range", {})
        overlay_range = overlay_sym.get("range", {})

        # Simple heuristic: if range changed, body likely changed
        if base_range != overlay_range:
            return True

        # TODO: More sophisticated check (AST comparison)
        return False

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content"""
        return hashlib.sha256(content.encode()).hexdigest()

    def _generate_overlay_id(self, base_snapshot_id: str, uncommitted_files: Dict[str, str]) -> str:
        """Generate unique overlay snapshot ID"""
        # Hash of base + all file paths + content hashes
        hasher = hashlib.sha256()
        hasher.update(base_snapshot_id.encode())

        for path in sorted(uncommitted_files.keys()):
            hasher.update(path.encode())
            hasher.update(self._compute_hash(uncommitted_files[path]).encode())

        return f"overlay_{hasher.hexdigest()[:16]}"


class InvalidationComputer:
    """
    Compute which base IR components need invalidation
    due to overlay changes
    """

    def __init__(self, graph_store):
        """
        Args:
            graph_store: KuzuGraphStore for querying dependencies
        """
        self.graph_store = graph_store

    async def compute_invalidated_files(self, overlay: OverlaySnapshot, repo_id: str) -> Set[str]:
        """
        Compute which base files are invalidated by overlay

        A base file is invalidated if:
        - It imports an overlay file
        - It calls a function from an overlay file
        - It inherits from an overlay class

        Returns:
            Set of file paths that need re-merging
        """
        invalidated = set()

        for affected_symbol in overlay.affected_symbols:
            # Find callers
            callers = await self._find_callers(affected_symbol, repo_id)
            for caller_symbol in callers:
                # Get file of caller
                caller_file = await self._get_symbol_file(caller_symbol, repo_id)
                if caller_file and caller_file not in overlay.uncommitted_files:
                    # Base file depends on overlay symbol
                    invalidated.add(caller_file)

            # Find importers
            importers = await self._find_importers(affected_symbol, repo_id)
            for importer_file in importers:
                if importer_file not in overlay.uncommitted_files:
                    invalidated.add(importer_file)

        overlay.invalidated_files = invalidated

        logger.info(
            "invalidated_files_computed",
            num_affected_symbols=len(overlay.affected_symbols),
            num_invalidated_files=len(invalidated),
        )

        return invalidated

    async def _find_callers(self, symbol_id: str, repo_id: str) -> Set[str]:
        """Find symbols that call this symbol"""
        # Query call graph
        query = f"""
        MATCH (caller:Symbol)-[:CALLS]->(callee:Symbol {{id: '{symbol_id}'}})
        WHERE caller.repo_id = '{repo_id}'
        RETURN caller.id as caller_id
        """

        try:
            results = await self.graph_store.execute_query(query)
            return {r["caller_id"] for r in results}
        except Exception as e:
            logger.error("failed_to_find_callers", symbol_id=symbol_id, error=str(e))
            return set()

    async def _find_importers(self, symbol_id: str, repo_id: str) -> Set[str]:
        """Find files that import this symbol"""
        query = f"""
        MATCH (file:File)-[:IMPORTS]->(symbol:Symbol {{id: '{symbol_id}'}})
        WHERE file.repo_id = '{repo_id}'
        RETURN file.path as file_path
        """

        try:
            results = await self.graph_store.execute_query(query)
            return {r["file_path"] for r in results}
        except Exception as e:
            logger.error("failed_to_find_importers", symbol_id=symbol_id, error=str(e))
            return set()

    async def _get_symbol_file(self, symbol_id: str, repo_id: str) -> Optional[str]:
        """Get file path for symbol"""
        query = f"""
        MATCH (symbol:Symbol {{id: '{symbol_id}', repo_id: '{repo_id}'}})
        RETURN symbol.file as file_path
        """

        try:
            results = await self.graph_store.execute_query(query)
            if results:
                return results[0]["file_path"]
        except Exception as e:
            logger.error("failed_to_get_symbol_file", symbol_id=symbol_id, error=str(e))

        return None
