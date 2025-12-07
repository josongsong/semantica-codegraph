"""
Overlay IR Builder

Builds IR from uncommitted files and computes delta against base.
"""

import hashlib
from datetime import datetime
from pathlib import Path

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder

from .models import (
    OverlayConfig,
    OverlaySnapshot,
    UncommittedFile,
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
        ir_builder: SOTAIRBuilder | None = None,  # SOTA IR Builder
        config: OverlayConfig | None = None,
        project_root: Path | None = None,
    ):
        self.project_root = project_root or Path.cwd()
        self.ir_builder = ir_builder or SOTAIRBuilder(project_root=self.project_root)
        self.config = config or OverlayConfig()

    async def build_overlay(
        self,
        base_snapshot_id: str,
        repo_id: str,
        uncommitted_files: dict[str, str],  # path -> content
        base_ir_docs: dict[str, dict] | None = None,
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
        self, overlay: OverlaySnapshot, file_path: str, content: str, base_ir_docs: dict[str, dict] | None
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
            # Use SOTA IR Builder to build IR for single file
            # For now, use simplified approach - just build structural IR
            file_path_obj = Path(file_path)
            ir_docs, _, _ = await self.ir_builder.build_full(files=[file_path_obj])

            if file_path in ir_docs:
                ir_doc_obj = ir_docs[file_path]
                # Convert IRDocument to dict
                ir_doc = self._ir_document_to_dict(ir_doc_obj)
            else:
                # Fallback: create minimal IR
                ir_doc = {"file": file_path, "symbols": []}
                logger.warning("failed_to_build_ir", file_path=file_path, reason="not_in_result")

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

    def _compute_affected_symbols(self, base_ir: dict, overlay_ir: dict) -> set[str]:
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
        """Check if symbol body changed using semantic hash"""
        # Method 1: Semantic hash comparison (faster than full AST)
        base_hash = self._compute_semantic_hash(base_sym)
        overlay_hash = self._compute_semantic_hash(overlay_sym)

        if base_hash != overlay_hash:
            return True

        # Method 2: Range comparison as fallback
        base_range = base_sym.get("range", {})
        overlay_range = overlay_sym.get("range", {})

        return base_range != overlay_range

    def _compute_semantic_hash(self, symbol: dict) -> str:
        """Compute semantic hash ignoring whitespace and comments"""
        import re

        # Get signature + body representation
        signature = symbol.get("signature", "")
        body_repr = symbol.get("body", "")

        # Normalize: remove whitespace, comments
        normalized = re.sub(r"\s+", "", signature + body_repr)
        normalized = re.sub(r"#.*$", "", normalized, flags=re.MULTILINE)

        # Hash
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _ir_document_to_dict(self, ir_doc) -> dict:
        """Convert IRDocument object to dict"""
        try:
            # If it's already a dict, return it
            if isinstance(ir_doc, dict):
                return ir_doc

            # Convert IRDocument to dict
            result = {
                "file": getattr(ir_doc, "file", ""),
                "symbols": [],
            }

            # Extract symbols if available
            if hasattr(ir_doc, "symbols"):
                symbols = ir_doc.symbols
                for symbol in symbols:
                    sym_dict = {
                        "id": getattr(symbol, "id", ""),
                        "name": getattr(symbol, "name", ""),
                        "signature": getattr(symbol, "signature", ""),
                    }
                    result["symbols"].append(sym_dict)

            return result

        except Exception as e:
            logger.warning("ir_document_conversion_failed", error=str(e))
            return {"file": "", "symbols": []}

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content"""
        return hashlib.sha256(content.encode()).hexdigest()

    def _generate_overlay_id(self, base_snapshot_id: str, uncommitted_files: dict[str, str]) -> str:
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

    async def compute_invalidated_files(self, overlay: OverlaySnapshot, repo_id: str) -> set[str]:
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

    async def _find_callers(self, symbol_id: str, repo_id: str) -> set[str]:
        """Find symbols that call this symbol"""
        # Parameterized query to prevent SQL injection
        query = """
        MATCH (caller:Symbol)-[:CALLS]->(callee:Symbol {id: $symbol_id})
        WHERE caller.repo_id = $repo_id
        RETURN caller.id as caller_id
        """
        params = {"symbol_id": symbol_id, "repo_id": repo_id}

        try:
            results = await self.graph_store.execute_query(query, params)
            return {r["caller_id"] for r in results}
        except Exception as e:
            logger.error("failed_to_find_callers", symbol_id=symbol_id, error=str(e))
            return set()

    async def _find_importers(self, symbol_id: str, repo_id: str) -> set[str]:
        """Find files that import this symbol"""
        query = """
        MATCH (file:File)-[:IMPORTS]->(symbol:Symbol {id: $symbol_id})
        WHERE file.repo_id = $repo_id
        RETURN file.path as file_path
        """
        params = {"symbol_id": symbol_id, "repo_id": repo_id}

        try:
            results = await self.graph_store.execute_query(query, params)
            return {r["file_path"] for r in results}
        except Exception as e:
            logger.error("failed_to_find_importers", symbol_id=symbol_id, error=str(e))
            return set()

    async def _get_symbol_file(self, symbol_id: str, repo_id: str) -> str | None:
        """Get file path for symbol"""
        query = """
        MATCH (symbol:Symbol {id: $symbol_id, repo_id: $repo_id})
        RETURN symbol.file as file_path
        """
        params = {"symbol_id": symbol_id, "repo_id": repo_id}

        try:
            results = await self.graph_store.execute_query(query, params)
            if results:
                return results[0]["file_path"]
        except Exception as e:
            logger.error("failed_to_get_symbol_file", symbol_id=symbol_id, error=str(e))

        return None
