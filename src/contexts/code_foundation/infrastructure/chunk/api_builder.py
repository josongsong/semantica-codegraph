"""
Module API Chunk Builder (GAP #5)

Builds cross-file chunk relationships:
- Module-level public API chunks from __all__ exports
- Interface chunks for cross-file protocols
- Re-export chunks for symbol forwarding

Usage:
    api_builder = ModuleAPIBuilder(id_generator)
    api_chunks = api_builder.build_module_api(
        module_chunks=module_chunks,
        file_chunks=file_chunks,
        ir_docs=ir_docs,  # All IR docs in module
        repo_id="myrepo",
        snapshot_id="abc123",
    )
"""

from typing import TYPE_CHECKING

from src.contexts.code_foundation.infrastructure.chunk.id_generator import ChunkIdContext, ChunkIdGenerator
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, CrossFileRelation, ModuleAPIChunk

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
from src.common.observability import get_logger

logger = get_logger(__name__)


class ModuleAPIBuilder:
    """
    Builds module-level API chunks from file exports.

    GAP #5: Creates cross-file chunk relationships for:
    - Python __all__ exports
    - TypeScript/JavaScript export statements
    - Go/Rust public declarations
    """

    def __init__(self, id_generator: ChunkIdGenerator):
        self._id_gen = id_generator

    def build_module_api(
        self,
        module_chunks: list[Chunk],
        file_chunks: list[Chunk],
        ir_docs: list["IRDocument"],
        repo_id: str,
        snapshot_id: str,
    ) -> tuple[list[Chunk], list[ModuleAPIChunk], list[CrossFileRelation]]:
        """
        Build module API chunks from file exports.

        Args:
            module_chunks: Module-level chunks
            file_chunks: File-level chunks
            ir_docs: All IR documents in the module
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Tuple of (api_chunks, module_api_infos, cross_file_relations)
        """
        api_chunks: list[Chunk] = []
        module_api_infos: list[ModuleAPIChunk] = []
        cross_file_relations: list[CrossFileRelation] = []

        # Group files by module
        files_by_module: dict[str, list[Chunk]] = {}
        for file_chunk in file_chunks:
            module_path = file_chunk.module_path or "default"
            if module_path not in files_by_module:
                files_by_module[module_path] = []
            files_by_module[module_path].append(file_chunk)

        # Group IR docs by file path
        ir_by_file: dict[str, IRDocument] = {}
        for ir_doc in ir_docs:
            for node in ir_doc.nodes:
                if node.file_path:
                    ir_by_file[node.file_path] = ir_doc
                    break

        # Build API chunk for each module
        for module_chunk in module_chunks:
            module_path = module_chunk.module_path
            if not module_path:
                continue

            module_files = files_by_module.get(module_path, [])
            if not module_files:
                continue

            # Collect exports from all files in module
            exported_symbols: dict[str, str] = {}  # symbol_id → file_path
            reexported_symbols: dict[str, str] = {}  # symbol_id → source_module

            for file_chunk in module_files:
                file_path = file_chunk.file_path
                if not file_path:
                    continue

                ir_doc = ir_by_file.get(file_path)
                if not ir_doc:
                    continue

                # Extract exports based on language
                language = file_chunk.language or "python"
                file_exports, file_reexports = self._extract_exports(ir_doc, file_path, language)

                exported_symbols.update(file_exports)
                reexported_symbols.update(file_reexports)

            # Skip if no exports
            if not exported_symbols and not reexported_symbols:
                continue

            # Create module_api chunk
            fqn = f"{module_path}.__api__"
            ctx = ChunkIdContext(repo_id=repo_id, kind="module_api", fqn=fqn)
            chunk_id = self._id_gen.generate(ctx)

            api_chunk = Chunk(
                chunk_id=chunk_id,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                project_id=module_chunk.project_id,
                module_path=module_path,
                file_path=None,  # Cross-file - no single file
                kind="module_api",
                fqn=fqn,
                start_line=None,  # No line range
                end_line=None,
                original_start_line=None,
                original_end_line=None,
                content_hash=None,
                parent_id=module_chunk.chunk_id,
                children=list(exported_symbols.keys()),  # Symbol IDs as children
                language=module_chunk.language,
                symbol_visibility="public",
                symbol_id=None,
                symbol_owner_id=None,
                summary=f"Public API for module {module_path}",
                importance=0.8,  # API surfaces are important
                attrs={
                    "export_count": len(exported_symbols),
                    "reexport_count": len(reexported_symbols),
                },
            )

            api_chunks.append(api_chunk)

            # Create ModuleAPIChunk info
            module_api_info = ModuleAPIChunk(
                chunk_id=chunk_id,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                module_path=module_path,
                exported_symbols=exported_symbols,
                reexported_symbols=reexported_symbols,
            )
            module_api_infos.append(module_api_info)

            # Create cross-file relations for re-exports
            for symbol_id, source_module in reexported_symbols.items():
                relation = CrossFileRelation(
                    source_chunk_id=chunk_id,
                    target_chunk_id=f"chunk:{repo_id}:module:{source_module}",  # Target module
                    relation_type="reexports",
                    symbol_id=symbol_id,
                )
                cross_file_relations.append(relation)

            # Link module chunk to API chunk
            module_chunk.children.append(chunk_id)

        logger.info(
            f"GAP #5: Built {len(api_chunks)} module API chunks, {len(cross_file_relations)} cross-file relations"
        )

        return api_chunks, module_api_infos, cross_file_relations

    def _extract_exports(
        self, ir_doc: "IRDocument", file_path: str, language: str
    ) -> tuple[dict[str, str], dict[str, str]]:
        """
        Extract exports from IR document.

        Args:
            ir_doc: IR document
            file_path: File path
            language: Programming language

        Returns:
            Tuple of (exported_symbols, reexported_symbols)
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        exported_symbols: dict[str, str] = {}
        reexported_symbols: dict[str, str] = {}

        if language == "python":
            # Look for __all__ variable
            for node in ir_doc.nodes:
                if node.file_path != file_path:
                    continue

                # Check for __all__ in module
                if node.kind == NodeKind.VARIABLE and node.name == "__all__":
                    # Parse __all__ list from attrs
                    all_exports = node.attrs.get("value", [])
                    if isinstance(all_exports, list):
                        for export_name in all_exports:
                            # Find the symbol with this name
                            for symbol_node in ir_doc.nodes:
                                if symbol_node.file_path == file_path and symbol_node.name == export_name:
                                    exported_symbols[symbol_node.id] = file_path
                                    break

                # Check for re-exports (from X import Y pattern)
                if node.kind == NodeKind.IMPORT:
                    if node.attrs.get("is_reexport", False):
                        source_module = node.attrs.get("source_module", "")
                        for exported_name in node.attrs.get("exported_names", []):
                            symbol_id = f"{file_path}:{exported_name}"
                            reexported_symbols[symbol_id] = source_module

        elif language in ("typescript", "javascript"):
            # Look for export statements
            for node in ir_doc.nodes:
                if node.file_path != file_path:
                    continue

                if node.attrs.get("exported", False):
                    exported_symbols[node.id] = file_path

                # Check for re-exports (export { X } from 'Y')
                if node.kind == NodeKind.IMPORT and node.attrs.get("is_reexport", False):
                    source_module = node.attrs.get("source_module", "")
                    reexported_symbols[node.id] = source_module

        elif language == "go":
            # Public symbols start with uppercase
            for node in ir_doc.nodes:
                if node.file_path != file_path:
                    continue

                if node.name and node.name[0].isupper():
                    if node.kind in (NodeKind.FUNCTION, NodeKind.CLASS, NodeKind.VARIABLE):
                        exported_symbols[node.id] = file_path

        return exported_symbols, reexported_symbols

    def build_cross_file_relations(
        self,
        chunks: list[Chunk],
        ir_docs: list["IRDocument"],
    ) -> list[CrossFileRelation]:
        """
        Build cross-file relations from import/extend/implement statements.

        Args:
            chunks: All chunks
            ir_docs: All IR documents

        Returns:
            List of cross-file relations
        """
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        relations: list[CrossFileRelation] = []

        # Build chunk lookup by file path and symbol
        chunk_by_file: dict[str, Chunk] = {}
        chunk_by_symbol: dict[str, Chunk] = {}

        for chunk in chunks:
            if chunk.file_path:
                chunk_by_file[chunk.file_path] = chunk
            if chunk.symbol_id:
                chunk_by_symbol[chunk.symbol_id] = chunk

        # Analyze IR for cross-file references
        for ir_doc in ir_docs:
            for node in ir_doc.nodes:
                source_chunk = chunk_by_symbol.get(node.id)
                if not source_chunk:
                    continue

                # Check for inheritance (extends)
                if node.kind == NodeKind.CLASS:
                    for base_id in node.attrs.get("base_classes", []):
                        target_chunk = chunk_by_symbol.get(base_id)
                        if target_chunk and target_chunk.file_path != source_chunk.file_path:
                            relations.append(
                                CrossFileRelation(
                                    source_chunk_id=source_chunk.chunk_id,
                                    target_chunk_id=target_chunk.chunk_id,
                                    relation_type="extends",
                                    symbol_id=base_id,
                                )
                            )

                    # Check for interface implementation
                    for iface_id in node.attrs.get("implements", []):
                        target_chunk = chunk_by_symbol.get(iface_id)
                        if target_chunk and target_chunk.file_path != source_chunk.file_path:
                            relations.append(
                                CrossFileRelation(
                                    source_chunk_id=source_chunk.chunk_id,
                                    target_chunk_id=target_chunk.chunk_id,
                                    relation_type="implements",
                                    symbol_id=iface_id,
                                )
                            )

                # Check for imports
                if node.kind == NodeKind.IMPORT:
                    imported_module = node.attrs.get("module_path", "")
                    if imported_module:
                        # Find target module chunk
                        for chunk in chunks:
                            if chunk.kind == "module" and chunk.module_path == imported_module:
                                relations.append(
                                    CrossFileRelation(
                                        source_chunk_id=source_chunk.chunk_id,
                                        target_chunk_id=chunk.chunk_id,
                                        relation_type="imports",
                                        symbol_id=node.id,
                                    )
                                )
                                break

        logger.debug(f"GAP #5: Built {len(relations)} cross-file relations from IR")
        return relations
