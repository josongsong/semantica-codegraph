"""
Process File UseCase

파일 전체 처리 (AST → IR → Graph → Chunks)
"""

from pathlib import Path

from ..domain.models import Chunk, GraphDocument, IRDocument, Language
from ..domain.ports import ChunkerPort, GraphBuilderPort, IRGeneratorPort, ParserPort


class ProcessFileUseCase:
    """파일 전체 처리 UseCase"""

    def __init__(
        self,
        parser: ParserPort,
        ir_generator: IRGeneratorPort,
        graph_builder: GraphBuilderPort,
        chunker: ChunkerPort,
    ):
        """
        초기화

        Args:
            parser: AST 파서
            ir_generator: IR 생성기
            graph_builder: 그래프 빌더
            chunker: 청커
        """
        self.parser = parser
        self.ir_generator = ir_generator
        self.graph_builder = graph_builder
        self.chunker = chunker

    def execute(
        self, file_path: Path, language: Language | None = None
    ) -> tuple[IRDocument, GraphDocument, list[Chunk]]:
        """
        파일 전체 처리 실행

        Args:
            file_path: 파일 경로
            language: 언어 (None이면 자동 감지)

        Returns:
            (IR 문서, 그래프 문서, 청크 리스트)
        """
        # 1. 언어 자동 감지
        if language is None:
            language = self._detect_language(file_path)

        # 2. AST 파싱
        ast_doc = self.parser.parse_file(file_path, language)

        # 3. IR 생성
        ir_doc = self.ir_generator.generate(ast_doc)

        # 4. 그래프 빌드
        graph_doc = self.graph_builder.build(ir_doc)

        # 5. 청킹
        chunks = self.chunker.chunk(ir_doc, ast_doc.source_code)

        return ir_doc, graph_doc, chunks

    def _detect_language(self, file_path: Path) -> Language:
        """언어 자동 감지"""
        ext = file_path.suffix.lower()

        mapping = {
            ".py": Language.PYTHON,
            ".js": Language.JAVASCRIPT,
            ".jsx": Language.JAVASCRIPT,
            ".ts": Language.TYPESCRIPT,
            ".tsx": Language.TYPESCRIPT,
            ".go": Language.GO,
            ".rs": Language.RUST,
            ".java": Language.JAVA,
            ".cpp": Language.CPP,
            ".cc": Language.CPP,
            ".cxx": Language.CPP,
        }

        return mapping.get(ext, Language.UNKNOWN)
