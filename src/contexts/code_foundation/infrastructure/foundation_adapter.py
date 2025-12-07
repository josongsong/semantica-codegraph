"""
Foundation Adapter

실제 foundation 모듈 어댑터
"""

from pathlib import Path

from ..domain.models import (
    ASTDocument,
    Chunk,
    GraphDocument,
    IRDocument,
    Language,
)
from .adapters.converters import ModelConverter
from .parsing.source_file import SourceFile


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
        from .parsing.ast_tree import AstTree

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
        from .ir.models.core import EdgeKind, NodeKind

        # Foundation의 Node를 Domain의 Symbol로 변환
        symbols = []
        for node in foundation_ir.nodes:
            if node.kind in [NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD]:
                symbols.append(ModelConverter.foundation_node_to_domain_symbol(node))

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
            imports=[],  # TODO: Foundation의 import 정보 변환
            exports=[],  # TODO: Foundation의 export 정보 변환
            metadata={
                "ir_version": foundation_ir.schema_version,
                "node_count": len(foundation_ir.nodes),
                "edge_count": len(foundation_ir.edges),
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

    def chunk(self, ir_doc: IRDocument, source_code: str) -> list[Chunk]:
        """IR로부터 청크 생성"""
        file_lines = source_code.splitlines()

        # Foundation IRDocument와 GraphDocument 생성
        from .graph.models import GraphDocument as FoundationGraphDocument
        from .ir.models import IRDocument as FoundationIRDocument

        # Minimal Foundation IR
        foundation_nodes = [
            ModelConverter.domain_symbol_to_foundation_node(symbol, ir_doc.file_path, ir_doc.language.value)
            for symbol in ir_doc.symbols
        ]

        foundation_ir = FoundationIRDocument(
            repo_id="default",
            snapshot_id="default",
            schema_version="4.1.0",
            nodes=foundation_nodes,
            edges=[],
            types=[],
            signatures=[],
            meta={
                "file_path": ir_doc.file_path,
                "language": ir_doc.language.value,
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
                domain_chunks.append(
                    Chunk(
                        id=fchunk.id,
                        content=fchunk.content,
                        file_path=fchunk.file_path or ir_doc.file_path,
                        start_line=fchunk.start_line,
                        end_line=fchunk.end_line,
                        chunk_type=fchunk.chunk_type,
                        language=Language(fchunk.language) if fchunk.language else ir_doc.language,
                        metadata={
                            "content_hash": fchunk.content_hash,
                            "parent_chunk_id": fchunk.parent_chunk_id,
                        },
                    )
                )

            return domain_chunks
        except Exception as e:
            # 실패 시 간단한 파일 레벨 청크 반환
            print(f"Warning: ChunkBuilder failed: {e}, returning simple file chunk")
            return [
                Chunk(
                    id=f"{ir_doc.file_path}::__file__",
                    content=source_code[: min(1000, len(source_code))],
                    file_path=ir_doc.file_path,
                    start_line=1,
                    end_line=len(file_lines),
                    chunk_type="file",
                    language=ir_doc.language,
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

    def build(self, ir_doc: IRDocument) -> GraphDocument:
        """IR로부터 그래프 생성"""
        from .ir.models import IRDocument as FoundationIRDocument

        # Domain symbols를 Foundation nodes로 변환
        foundation_nodes = [
            ModelConverter.domain_symbol_to_foundation_node(symbol, ir_doc.file_path, ir_doc.language.value)
            for symbol in ir_doc.symbols
        ]

        # Domain references를 Foundation edges로 변환
        foundation_edges = [ModelConverter.domain_reference_to_foundation_edge(ref) for ref in ir_doc.references]

        foundation_ir = FoundationIRDocument(
            repo_id="default",
            snapshot_id="default",
            schema_version="4.1.0",
            nodes=foundation_nodes,
            edges=foundation_edges,
            types=[],
            signatures=[],
            meta={
                "file_path": ir_doc.file_path,
                "language": ir_doc.language.value,
            },
        )

        # GraphBuilder 호출 (semantic_snapshot 없이 structural graph만)
        foundation_graph = self.builder.build_full(
            ir_doc=foundation_ir,
            semantic_snapshot=None,  # Structural graph only
        )

        # Foundation GraphDocument를 Domain GraphDocument로 변환
        domain_nodes = [
            ModelConverter.foundation_graph_node_to_domain_node(fnode, ir_doc.file_path)
            for fnode in foundation_graph.graph_nodes.values()
        ]

        domain_edges = [
            ModelConverter.foundation_graph_edge_to_domain_edge(fedge) for fedge in foundation_graph.graph_edges
        ]

        return GraphDocument(
            file_path=ir_doc.file_path,
            nodes=domain_nodes,
            edges=domain_edges,
        )
