"""
Foundation Adapter

실제 foundation 모듈 어댑터
"""

from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

from ..domain.models import (
    ASTDocument,
    Chunk,
    IRDocument,
    Language,
)
from ..infrastructure.adapters.converters import ModelConverter
from ..infrastructure.graph.models import GraphDocument
from ..infrastructure.parsing.source_file import SourceFile

logger = get_logger(__name__)


def _get_nodes_or_convert_symbols(ir_doc: Any, converter: type = ModelConverter) -> list:
    """
    Get nodes from IRDocument (shared utility).

    Supports:
    - Infrastructure IRDocument (nodes field) - returns directly
    - Domain IRDocument (symbols field) - converts to nodes (DEPRECATED)

    Type Detection:
    - Infrastructure: has 'repo_id' or 'schema_version' field
    - Domain: has 'symbols' field without 'repo_id'

    Args:
        ir_doc: IRDocument (Domain or Infrastructure)
        converter: ModelConverter class for symbol→node conversion

    Returns:
        List of nodes (Infrastructure Node objects)
    """
    # Infrastructure IRDocument: has repo_id/schema_version + nodes field
    # NOTE: Check repo_id first to distinguish from Domain (more reliable than just 'nodes')
    if hasattr(ir_doc, "repo_id") and hasattr(ir_doc, "nodes"):
        return ir_doc.nodes  # Returns list (even if empty)

    # Domain IRDocument: has symbols field (DEPRECATED)
    if hasattr(ir_doc, "symbols"):
        file_path = getattr(ir_doc, "file_path", "")
        language = getattr(ir_doc, "language", None)
        lang_value = language.value if hasattr(language, "value") else str(language) if language else ""
        return [converter.domain_symbol_to_foundation_node(symbol, file_path, lang_value) for symbol in ir_doc.symbols]

    return []


def _get_edges_or_convert_references(ir_doc: Any, converter: type = ModelConverter) -> list:
    """
    Get edges from IRDocument (shared utility).

    Supports:
    - Infrastructure IRDocument (edges field) - returns directly
    - Domain IRDocument (references field) - converts to edges (DEPRECATED)
    """
    # Infrastructure IRDocument: has repo_id + edges field
    if hasattr(ir_doc, "repo_id") and hasattr(ir_doc, "edges"):
        return ir_doc.edges  # Returns list (even if empty)

    # Domain IRDocument: convert references to edges (DEPRECATED)
    if hasattr(ir_doc, "references"):
        return [converter.domain_reference_to_foundation_edge(ref) for ref in ir_doc.references]

    return []


def _get_ir_file_path(ir_doc: Any) -> str:
    """Get file path from IRDocument (Domain or Infrastructure)"""
    if hasattr(ir_doc, "file_path") and ir_doc.file_path:
        return ir_doc.file_path
    if hasattr(ir_doc, "meta") and ir_doc.meta:
        return ir_doc.meta.get("file_path", "")
    return ""


def _get_ir_language(ir_doc: Any) -> tuple[Any, str]:
    """Get language from IRDocument, returns (Language enum or None, string value)"""
    language = getattr(ir_doc, "language", None)
    lang_value = language.value if hasattr(language, "value") else str(language) if language else ""
    return language, lang_value


class FoundationParserAdapter:
    """실제 ParserRegistry 어댑터"""

    def __init__(self, parser_registry):
        """
        초기화

        Args:
            parser_registry: ParserRegistry 인스턴스
        """
        self.registry = parser_registry

    def parse_file(self, file_path: Path, language: Language) -> ASTDocument:
        """파일 파싱"""
        parser = self.registry.get_parser(language.value)
        source_code = file_path.read_text()
        tree = parser.parse(bytes(source_code, "utf8"))

        return ASTDocument(
            file_path=str(file_path),
            language=language,
            source_code=source_code,
            tree=tree,
            metadata={"parser": "tree-sitter"},
        )

    def parse_code(self, code: str, language: Language) -> ASTDocument:
        """코드 파싱"""
        parser = self.registry.get_parser(language.value)
        tree = parser.parse(bytes(code, "utf8"))

        return ASTDocument(
            file_path="<string>",
            language=language,
            source_code=code,
            tree=tree,
            metadata={"parser": "tree-sitter"},
        )


class FoundationIRGeneratorAdapter:
    """실제 PythonIRGenerator 어댑터"""

    def __init__(self, ir_generator, repo_id: str = "default"):
        """
        초기화

        Args:
            ir_generator: PythonIRGenerator 인스턴스
            repo_id: Repository ID
        """
        self.generator = ir_generator
        self.repo_id = repo_id

    def generate(self, ast_doc: ASTDocument) -> IRDocument:
        """AST로부터 IR 생성"""
        # ASTDocument를 SourceFile로 변환
        source = SourceFile.from_content(
            file_path=ast_doc.file_path,
            content=ast_doc.source_code,
            language=ast_doc.language.value,
        )

        # IR 생성 (tree-sitter AST 재사용)
        from ..infrastructure.parsing.ast_tree import AstTree

        ast_tree = AstTree(source, ast_doc.tree)

        ir_doc = self.generator.generate(
            source=source,
            snapshot_id="default",
            ast=ast_tree,
        )

        # Foundation IRDocument를 Domain IRDocument로 변환
        return self._convert_ir_document(ir_doc, ast_doc)

    def _convert_ir_document(self, foundation_ir: "IRDocument", ast_doc: ASTDocument) -> IRDocument:
        """Foundation IRDocument를 Domain IRDocument로 변환"""
        from ..infrastructure.ir.models.core import EdgeKind, NodeKind

        # Foundation의 Node를 Domain의 Symbol/Import/Export로 변환
        symbols = []
        imports = []
        exports = []

        for node in foundation_ir.nodes:
            if node.kind in [NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD]:
                symbols.append(ModelConverter.foundation_node_to_domain_symbol(node))
            elif node.kind == NodeKind.IMPORT:
                # Import node: fqn 또는 name 사용
                import_name = node.fqn or node.name or ""
                if import_name:
                    imports.append(import_name)
            elif node.kind == NodeKind.EXPORT:
                # Export node: fqn 또는 name 사용
                export_name = node.fqn or node.name or ""
                if export_name:
                    exports.append(export_name)

        # Edge에서 IMPORTS 관계도 추출
        for edge in foundation_ir.edges:
            if edge.kind == EdgeKind.IMPORTS:
                # target_id가 import된 모듈/심볼
                if edge.target_id and edge.target_id not in imports:
                    imports.append(edge.target_id)

        # Edge를 Reference로 변환
        references = []
        for edge in foundation_ir.edges:
            if edge.kind == EdgeKind.CALLS:
                references.append(ModelConverter.foundation_edge_to_domain_reference(edge))

        return IRDocument(
            file_path=ast_doc.file_path,
            language=ast_doc.language,
            symbols=symbols,
            references=references,
            imports=imports,
            exports=exports,
            metadata={
                "ir_version": foundation_ir.schema_version,
                "node_count": len(foundation_ir.nodes),
                "edge_count": len(foundation_ir.edges),
                "import_count": len(imports),
                "export_count": len(exports),
            },
        )


class FoundationChunkerAdapter:
    """실제 ChunkBuilder 어댑터"""

    def __init__(self, chunk_builder):
        """
        초기화

        Args:
            chunk_builder: ChunkBuilder 인스턴스
        """
        self.builder = chunk_builder

    def chunk(self, ir_doc, source_code: str) -> list[Chunk]:
        """IR로부터 청크 생성"""
        file_lines = source_code.splitlines()

        # Extract file_path and language using shared utilities
        file_path = _get_ir_file_path(ir_doc)
        language, lang_value = _get_ir_language(ir_doc)

        # Foundation IRDocument와 GraphDocument 생성
        from ..infrastructure.graph.models import GraphDocument as FoundationGraphDocument
        from ..infrastructure.ir.models import IRDocument as FoundationIRDocument

        # Get or convert nodes
        foundation_nodes = _get_nodes_or_convert_symbols(ir_doc)

        foundation_ir = FoundationIRDocument(
            repo_id="default",
            snapshot_id="default",
            schema_version="4.1.0",
            nodes=foundation_nodes,
            edges=[],
            types=[],
            signatures=[],
            meta={
                "file_path": file_path,
                "language": lang_value,
            },
        )

        # Minimal Foundation Graph
        foundation_graph = FoundationGraphDocument(
            repo_id="default",
            snapshot_id="default",
        )

        # ChunkBuilder 호출
        try:
            foundation_chunks, _, _ = self.builder.build(
                repo_id="default",
                ir_doc=foundation_ir,
                graph_doc=foundation_graph,
                file_text=file_lines,
                repo_config={"project_roots": ["."]},
                snapshot_id="default",
            )

            # Foundation Chunk를 Domain Chunk로 변환
            domain_chunks = []
            for fchunk in foundation_chunks:
                # Determine chunk language
                chunk_lang = language
                if fchunk.language:
                    try:
                        chunk_lang = Language(fchunk.language)
                    except ValueError:
                        pass

                domain_chunks.append(
                    Chunk(
                        id=fchunk.id,
                        content=fchunk.content,
                        file_path=fchunk.file_path or file_path,
                        start_line=fchunk.start_line,
                        end_line=fchunk.end_line,
                        chunk_type=fchunk.chunk_type,
                        language=chunk_lang,
                        metadata={
                            "content_hash": fchunk.content_hash,
                            "parent_chunk_id": fchunk.parent_chunk_id,
                        },
                    )
                )

            return domain_chunks
        except Exception as e:
            # 실패 시 간단한 파일 레벨 청크 반환
            logger.warning(f"ChunkBuilder failed: {e}, returning simple file chunk")
            return [
                Chunk(
                    id=f"{file_path}::__file__",
                    content=source_code[: min(1000, len(source_code))],
                    file_path=file_path,
                    start_line=1,
                    end_line=len(file_lines),
                    chunk_type="file",
                    language=language,
                    metadata={},
                )
            ]


class FoundationGraphBuilderAdapter:
    """실제 GraphBuilder 어댑터"""

    def __init__(self, graph_builder):
        """
        초기화

        Args:
            graph_builder: GraphBuilder 인스턴스
        """
        self.builder = graph_builder

    def build(self, ir_doc) -> GraphDocument:
        """IR로부터 그래프 생성"""
        from ..infrastructure.ir.models import IRDocument as FoundationIRDocument

        # Get or convert nodes and edges using shared utilities
        foundation_nodes = _get_nodes_or_convert_symbols(ir_doc)
        foundation_edges = _get_edges_or_convert_references(ir_doc)

        # Get file path and language using shared utilities
        file_path = _get_ir_file_path(ir_doc)
        _, lang_value = _get_ir_language(ir_doc)

        foundation_ir = FoundationIRDocument(
            repo_id="default",
            snapshot_id="default",
            schema_version="4.1.0",
            nodes=foundation_nodes,
            edges=foundation_edges,
            types=[],
            signatures=[],
            meta={
                "file_path": file_path,
                "language": lang_value,
            },
        )

        # GraphBuilder 호출 (semantic_snapshot 없이 structural graph만)
        foundation_graph = self.builder.build_full(
            ir_doc=foundation_ir,
            semantic_snapshot=None,  # Structural graph only
        )

        # Foundation GraphDocument를 Domain GraphDocument로 변환
        domain_nodes = [
            ModelConverter.foundation_graph_node_to_domain_node(fnode, file_path)
            for fnode in foundation_graph.graph_nodes.values()
        ]

        domain_edges = [
            ModelConverter.foundation_graph_edge_to_domain_edge(fedge) for fedge in foundation_graph.graph_edges
        ]

        return GraphDocument(
            file_path=file_path,
            nodes=domain_nodes,
            edges=domain_edges,
        )
