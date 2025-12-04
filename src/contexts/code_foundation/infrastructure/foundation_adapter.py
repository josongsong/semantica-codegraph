"""
Foundation Adapter

실제 foundation 모듈 어댑터
"""

from pathlib import Path

from ..domain.models import (
    ASTDocument,
    Chunk,
    GraphDocument,
    GraphEdge,
    GraphNode,
    IRDocument,
    Language,
)


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
        # 실제 parser 가져오기
        parser = self.registry.get_parser(language.value)

        # 소스 코드 읽기
        source_code = file_path.read_text()

        # 파싱
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
        # 실제 foundation에서 IRDocument를 받아 chunk 생성
        # foundation의 build 메서드 호출

        # IRDocument를 foundation 형식으로 변환 필요
        # 일단 간단한 매핑만

        # foundation chunk builder 호출
        # chunks = self.builder.build(ir_doc)

        # 임시: 파일 단위 청크만 생성
        chunk_id = f"{ir_doc.file_path}::__file__"

        return [
            Chunk(
                id=chunk_id,
                content=source_code[:1000],
                file_path=ir_doc.file_path,
                start_line=1,
                end_line=len(source_code.splitlines()),
                chunk_type="file",
                language=ir_doc.language,
                metadata={"source": "foundation"},
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
        # 실제 foundation graph builder 호출
        # graph_doc = self.builder.build_full(ir_doc)

        # 임시: 간단한 그래프 생성
        nodes = []
        edges = []

        # 파일 노드
        file_node_id = f"file::{ir_doc.file_path}"
        nodes.append(
            GraphNode(
                id=file_node_id,
                type="file",
                name=ir_doc.file_path,
                file_path=ir_doc.file_path,
                start_line=1,
                end_line=1,
                properties={"language": ir_doc.language.value},
            )
        )

        # 심볼 노드
        for symbol in ir_doc.symbols:
            node_id = f"{ir_doc.file_path}::{symbol.name}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    type=symbol.type,
                    name=symbol.name,
                    file_path=ir_doc.file_path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    properties={"docstring": symbol.docstring or ""},
                )
            )

            # CONTAINS 엣지
            edges.append(
                GraphEdge(
                    source=file_node_id,
                    target=node_id,
                    type="CONTAINS",
                    properties={},
                )
            )

        return GraphDocument(
            file_path=ir_doc.file_path,
            nodes=nodes,
            edges=edges,
        )
